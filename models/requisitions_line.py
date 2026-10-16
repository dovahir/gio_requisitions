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
