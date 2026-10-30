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
        'requisition_line_ids.qty_cancelled',
        'requisition_line_ids.requisition_id.state',
        'cantidad_explosion'
    )
    def _compute_traceability_quantities(self):
        for rec in self:
            rec_sudo = rec.sudo()
            valid_lines = rec_sudo.requisition_line_ids.filtered(
                lambda l: l.requisition_id and l.requisition_id.state not in ('cancel', 'rejected')
            )
            net_demanded = max(0.0, sum(valid_lines.mapped('product_qty')) - sum(valid_lines.mapped('qty_cancelled')))
            done_qty = sum(valid_lines.mapped('qty_done'))

            rec.qty_requisited = net_demanded
            rec.qty_supplied = done_qty
            rec.qty_in_transit = max(0.0, net_demanded - done_qty)

