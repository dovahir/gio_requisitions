# -*- coding: utf-8 -*-
from markupsafe import Markup, escape
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ContractorExplosionRequisicionWizard(models.TransientModel):
    _name = 'contractor.explosion.requisicion.wizard'
    _description = 'Asistente de Creación de Requisición desde Explosión'

    proyecto_id = fields.Many2one(
        'contractor.proyecto',
        string='Proyecto GIO',
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Solicita',
        required=False,
        default=lambda self: self.env.user.employee_id,
        help='Empleado que realiza la solicitud del material para obra.',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Autoriza',
        required=False,
        domain=lambda self: self._domain_user_id(),
        help='Usuario responsable de aprobar la requisición.',
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén de Entrega',
        required=True,
        domain="[('company_id', '=', company_id)]",
        help='Almacén base que gestionará el surtido o compra de los insumos.',
    )
    date_required = fields.Date(
        string='Fecha Requerida en Sitio',
        required=True,
        default=fields.Date.context_today,
    )
    priority = fields.Selection(
        [
            ('normal', 'Normal'),
            ('urgent', 'Urgente'),
        ],
        string='Prioridad',
        default='normal',
        required=True,
    )
    note = fields.Text(
        string='Justificación / Observaciones',
    )
    line_ids = fields.One2many(
        'contractor.explosion.requisicion.wizard.line',
        'wizard_id',
        string='Insumos de Explosión',
    )

    @api.model
    def _domain_user_id(self):
        """Filtra usuarios autorizadores según los grupos de dh_requisitions."""
        group_approver = self.env.ref('dh_requisitions.group_requisitions_approver', raise_if_not_found=False)
        group_manager = self.env.ref('dh_requisitions.group_requisitions_manager', raise_if_not_found=False)
        group_ids = [g.id for g in (group_approver, group_manager) if g]
        if group_ids:
            return [('all_group_ids', 'in', group_ids), ('share', '=', False)]
        return [('share', '=', False)]

    def action_crear_requisicion(self):
        self.ensure_one()
        self.proyecto_id._validar_elegibilidad_requisiciones()

        if not self.employee_id:
            raise UserError(_('Debes seleccionar el empleado solicitante.'))
        if not self.user_id:
            raise UserError(_('Debes seleccionar el usuario autorizador.'))

        lineas_a_solicitar = self.line_ids.filtered(lambda l: l.product_qty > 0)
        if not lineas_a_solicitar:
            raise UserError(_('Debes ingresar una cantidad a solicitar mayor a cero en al menos un insumo.'))

        # 1. Validación estricta de tope presupuestal (Punto 4)
        for l in lineas_a_solicitar:
            disponible = max(0.0, l.cantidad_explosion - l.qty_requisited)
            if round(l.product_qty, 4) > round(disponible, 4):
                raise UserError(_(
                    'No se puede solicitar una cantidad mayor a lo planeado en la explosión de insumos.\n\n'
                    '• Producto: %s\n'
                    '• Presupuesto planeado: %s\n'
                    '• Ya requisitado previamente: %s\n'
                    '• Máximo disponible para pedir: %s\n'
                    '• Cantidad intentando solicitar: %s'
                ) % (
                    l.product_id.display_name,
                    l.cantidad_explosion,
                    l.qty_requisited,
                    disponible,
                    l.product_qty
                ))

        # 2. Mapeo y Fallback de Categorías de Requisición (Punto 7)
        tipo_map = {
            'material': 'material',
            'equipo': 'equipment',
            'seguridad_especial': 'equipment',
            'servicio_tercero': 'service',
            'mano_obra': 'service',
        }

        lineas_vals = []
        for l in lineas_a_solicitar:
            expected_type = tipo_map.get(l.partida_line_id.tipo_apu, 'material')
            product = l.product_id
            categ = product.categ_id

            if categ:
                if not categ.requisition_type or not categ.allow_requisition:
                    categ_vals = {}
                    if not categ.requisition_type:
                        categ_vals['requisition_type'] = expected_type
                    if not categ.allow_requisition:
                        categ_vals['allow_requisition'] = True
                    categ.sudo().write(categ_vals)
                tipo_linea = categ.requisition_type or expected_type
            else:
                tipo_linea = expected_type

            lineas_vals.append((0, 0, {
                'product_id': l.product_id.id,
                'product_qty': l.product_qty,
                'partida_line_id': l.partida_line_id.id,
                'line_type': tipo_linea,
                'priority': self.priority,
            }))

        req_vals = {
            'employee_id': self.employee_id.id,
            'user_id': self.user_id.id,
            'warehouse_id': self.warehouse_id.id,
            'company_id': self.company_id.id,
            'date_required': self.date_required,
            'priority': self.priority,
            'proyecto_id': self.proyecto_id.id,
            'state': 'draft',
            'line_ids': lineas_vals,
        }

        requisicion = self.env['requisitions'].create(req_vals)

        # Registro en el chatter del proyecto
        body_proyecto = Markup(_(
            'Se generó la requisición <b>%s</b> con %d insumos desde la explosión de obra.'
        )) % (escape(requisicion.name), len(lineas_vals))
        self.proyecto_id.message_post(body=body_proyecto, subtype_xmlid='mail.mt_note')

        # Registro en el chatter de la requisición
        body_req = Markup(_(
            'Requisición originada desde la Explosión de Insumos del proyecto <b>%s</b>.'
        )) % escape(self.proyecto_id.display_name)
        requisicion.message_post(body=body_req, subtype_xmlid='mail.mt_note')

        return {
            'name': _('Requisición de Obra'),
            'type': 'ir.actions.act_window',
            'res_model': 'requisitions',
            'res_id': requisicion.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }


class ContractorExplosionRequisicionWizardLine(models.TransientModel):
    _name = 'contractor.explosion.requisicion.wizard.line'
    _description = 'Línea de Insumo en Asistente de Requisición'

    wizard_id = fields.Many2one(
        'contractor.explosion.requisicion.wizard',
        string='Asistente',
        required=True,
        ondelete='cascade',
    )
    partida_line_id = fields.Many2one(
        'contractor.partida.line',
        string='Insumo de Explosión',
        required=True,
        readonly=True,
    )
    partida_id = fields.Many2one(
        'contractor.partida',
        string='Partida',
        related='partida_line_id.partida_id',
        readonly=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto / Insumo',
        related='partida_line_id.product_id',
        readonly=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom',
        string='UoM',
        related='product_id.uom_id',
        readonly=True,
    )
    cantidad_explosion = fields.Float(
        string='Presupuesto',
        readonly=True,
        digits='Product Unit of Measure',
    )
    qty_requisited = fields.Float(
        string='Requisitado',
        readonly=True,
        digits='Product Unit of Measure',
    )
    qty_disponible_planeada = fields.Float(
        string='Disponible',
        compute='_compute_qty_disponible_planeada',
        readonly=True,
        digits='Product Unit of Measure',
        help='Cantidad restante planeada en la explosión de insumos que aún no ha sido requisitada.',
    )
    product_qty = fields.Float(
        string='A Solicitar',
        default=0.0,
        digits='Product Unit of Measure',
    )

    @api.depends('cantidad_explosion', 'qty_requisited')
    def _compute_qty_disponible_planeada(self):
        for rec in self:
            rec.qty_disponible_planeada = max(0.0, rec.cantidad_explosion - rec.qty_requisited)

    @api.onchange('product_qty')
    def _onchange_product_qty(self):
        if self.product_qty < 0:
            self.product_qty = 0.0
            return {'warning': {
                'title': _('Cantidad inválida'),
                'message': _('La cantidad a solicitar no puede ser negativa.'),
            }}
        disponible = max(0.0, self.cantidad_explosion - self.qty_requisited)
        if round(self.product_qty, 4) > round(disponible, 4):
            excedente = self.product_qty
            self.product_qty = disponible
            return {'warning': {
                'title': _('Excede Presupuesto Disponible'),
                'message': _(
                    'No puedes solicitar %s unidades. Lo disponible según la explosión '
                    'de insumos es %s (Presupuesto: %s, Requisitado previo: %s).'
                ) % (excedente, disponible, self.cantidad_explosion, self.qty_requisited),
            }}
