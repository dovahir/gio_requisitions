# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ContractorPartidaLine(models.Model):
    _inherit = 'contractor.partida.line'

    requisition_line_ids = fields.One2many(
        'requisitions.line',
        'partida_line_id',
        string='Líneas de Requisición',
    )
    qty_requisited = fields.Float(
        string='Requisitado',
        compute='_compute_traceability_quantities',
        readonly=True,
        digits='Product Unit of Measure',
        help='Cantidad total solicitada en requisiciones de obra activas (excluye canceladas y rechazadas).',
    )
    qty_supplied = fields.Float(
        string='Suministrado',
        compute='_compute_traceability_quantities',
        readonly=True,
        digits='Product Unit of Measure',
        help='Cantidad física total entregada y recibida en obra vía requisition.allocation.',
    )
    qty_in_transit = fields.Float(
        string='En Tránsito',
        compute='_compute_traceability_quantities',
        readonly=True,
        digits='Product Unit of Measure',
        help='Cantidad requisitada que está en proceso de surtido o compra pero aún no ha sido entregada.',
    )

    @api.depends(
        'requisition_line_ids.product_qty',
        'requisition_line_ids.qty_done',
        'requisition_line_ids.requisition_id.state',
        'cantidad_explosion'
    )
    def _compute_traceability_quantities(self):
        for rec in self:
            rec_sudo = rec.sudo()
            valid_lines = rec_sudo.requisition_line_ids.filtered(
                lambda l: l.requisition_id and l.requisition_id.state not in ('cancel', 'rejected')
            )
            req_qty = sum(valid_lines.mapped('product_qty'))
            done_qty = sum(valid_lines.mapped('qty_done'))

            rec.qty_requisited = req_qty
            rec.qty_supplied = done_qty
            rec.qty_in_transit = max(0.0, req_qty - done_qty)

    def action_solicitar_requisicion_proyecto(self):
        """Dispara el asistente de requisición para el proyecto de las líneas o del contexto."""
        self.check_access('read')
        if not (self.env.is_admin() or self.env.user.has_group('dh_requisitions.group_requisitions_user')):
            raise UserError(_("Para solicitar requisiciones desde el proyecto, debes contar con el perfil de Usuario de Requisiciones."))
        proyecto = False
        selected = self.filtered(lambda l: not l.es_grupo and l.product_id)
        if self:
            proyectos = self.mapped('partida_id.proyecto_id')
            if proyectos:
                proyecto = proyectos[0]
        if not proyecto:
            p_id = (
                self.env.context.get('project_id')
                or self.env.context.get('default_proyecto_id')
                or (self.env.context.get('active_id') if self.env.context.get('active_model') == 'contractor.proyecto' else False)
            )
            if p_id:
                proyecto = self.env['contractor.proyecto'].browse(p_id)
        if not proyecto:
            raise UserError(_('No se encontró el proyecto asociado para generar la requisición.'))
        return proyecto.action_open_requisition_wizard(selected_lines=selected)

