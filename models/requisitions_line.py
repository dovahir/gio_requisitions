# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class RequisitionsLine(models.Model):
    _inherit = 'requisitions.line'

    partida_line_id = fields.Many2one(
        'contractor.partida.line',
        string='Insumo de Explosión',
        index=True,
        ondelete='set null',
        help='Línea de insumo en la explosión de APU del proyecto que originó este requerimiento.',
    )
    partida_id = fields.Many2one(
        'contractor.partida',
        string='Partida / Concepto',
        related='partida_line_id.partida_id',
        store=True,
        readonly=True,
        help='Partida o concepto presupuestal de la obra.',
    )

    @api.constrains('partida_line_id')
    def _check_partida_line_no_mano_obra(self):
        for line in self:
            if line.partida_line_id and line.partida_line_id.tipo_apu == 'mano_obra':
                raise ValidationError(_(
                    'No se permite requisitar insumos de Mano de Obra desde el flujo de requisiciones de obra. '
                    'La mano de obra no aplica para requisiciones de materiales/servicios.'
                ))

    @api.onchange('partida_line_id')
    def _onchange_partida_line_id(self):
        """Al seleccionar un insumo de la explosión, autocompleta el producto, tipo sugerido y cantidad."""
        if not self.partida_line_id:
            return

        linea = self.partida_line_id
        if linea.tipo_apu == 'mano_obra':
            self.partida_line_id = False
            return {'warning': {
                'title': _('Insumo no aplicable'),
                'message': _('Los insumos de Mano de Obra no aplican para el flujo de requisiciones de obra.'),
            }}

        if linea.product_id:
            self.product_id = linea.product_id

        # Mapeo sugerido de tipos APU a tipos de línea de requisición
        tipo_map = {
            'material': 'material',
            'equipo': 'equipment',
            'seguridad_especial': 'equipment',
            'servicio_tercero': 'service',
        }
        sugerido = tipo_map.get(linea.tipo_apu)
        if sugerido:
            self.line_type = sugerido
        elif not self.line_type:
            self.line_type = 'material'

        if not self.product_qty:
            self.product_qty = 1.0

    is_excedente_apu = fields.Boolean(
        string='¿Excedente de APU?',
        compute='_compute_excedente_apu',
        store=True,
        help='Indica si la cantidad solicitada excede la explosión presupuestal de APU del proyecto.'
    )
    qty_excedente_apu = fields.Float(
        string='Cantidad Excedente APU',
        compute='_compute_excedente_apu',
        store=True,
        digits='Product Unit of Measure',
        help='Cantidad que excede la explosión calculada en el APU.'
    )

    @api.depends(
        'product_qty',
        'qty_cancelled',
        'requisition_id.state',
        'partida_line_id',
        'partida_line_id.cantidad_explosion',
        'partida_line_id.requisition_line_ids.product_qty',
        'partida_line_id.requisition_line_ids.qty_cancelled',
        'partida_line_id.requisition_line_ids.requisition_id.state'
    )
    def _compute_excedente_apu(self):
        for line in self:
            if not line.partida_line_id or not line.partida_line_id.cantidad_explosion:
                line.is_excedente_apu = False
                line.qty_excedente_apu = 0.0
                continue

            explosion = line.partida_line_id.cantidad_explosion
            partida_line = line.partida_line_id
            otras_lineas = partida_line.requisition_line_ids.filtered(
                lambda l: l.id != line.id and l.requisition_id and l.requisition_id.state not in ('cancel', 'rejected')
            )
            prev_demanded = sum(otras_lineas.mapped('product_qty')) - sum(otras_lineas.mapped('qty_cancelled'))
            curr_demanded = line.product_qty - line.qty_cancelled if (not line.requisition_id or line.requisition_id.state not in ('cancel', 'rejected')) else 0.0
            total_demanded = max(0.0, prev_demanded + curr_demanded)

            if total_demanded > explosion:
                if prev_demanded >= explosion:
                    excedente_linea = curr_demanded
                else:
                    excedente_linea = total_demanded - explosion

                line.is_excedente_apu = excedente_linea > 0
                line.qty_excedente_apu = max(0.0, excedente_linea)
            else:
                line.is_excedente_apu = False
                line.qty_excedente_apu = 0.0

    @api.depends('sequence', 'requisition_id', 'line_type', 'requisition_id.proyecto_id')
    def _compute_sequence_number(self):
        proy_lines = self.filtered(lambda l: l.requisition_id and l.requisition_id.proyecto_id)
        other_lines = self - proy_lines
        if other_lines:
            super(RequisitionsLine, other_lines)._compute_sequence_number()
        for req in proy_lines.mapped('requisition_id'):
            lines = req.line_ids.sorted(key=lambda l: (l.sequence or 0, l.id or 0))
            seq = 1
            for l in lines:
                if l in self:
                    l.sequence_number = seq
                seq += 1
