# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


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

    @api.onchange('partida_line_id')
    def _onchange_partida_line_id(self):
        """Al seleccionar un insumo de la explosión, autocompleta el producto, tipo y cantidad sugerida."""
        if not self.partida_line_id:
            return

        linea = self.partida_line_id
        if linea.product_id:
            self.product_id = linea.product_id

        # Mapeo de tipos APU a tipos de línea de requisición
        tipo_map = {
            'material': 'material',
            'equipo': 'equipment',
            'seguridad_especial': 'equipment',
            'servicio_tercero': 'service',
            'mano_obra': 'service',
        }
        self.line_type = tipo_map.get(linea.tipo_apu, 'material')

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

    @api.depends('product_qty', 'partida_line_id', 'partida_line_id.cantidad_explosion')
    def _compute_excedente_apu(self):
        for line in self:
            if line.partida_line_id and line.partida_line_id.cantidad_explosion:
                explosion = line.partida_line_id.cantidad_explosion
                if line.product_qty > explosion:
                    line.is_excedente_apu = True
                    line.qty_excedente_apu = line.product_qty - explosion
                else:
                    line.is_excedente_apu = False
                    line.qty_excedente_apu = 0.0
            else:
                line.is_excedente_apu = False
                line.qty_excedente_apu = 0.0
