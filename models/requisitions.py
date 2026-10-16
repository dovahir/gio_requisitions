# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class Requisitions(models.Model):
    _inherit = 'requisitions'

    proyecto_id = fields.Many2one(
        'contractor.proyecto',
        string='Proyecto GIO',
        check_company=True,
        index=True,
        tracking=True,
        domain="[('is_requisition_eligible', '=', True)]",
        help='Proyecto de obra al cual se imputará este requerimiento de materiales o insumos. '
             'Solo se permiten proyectos confirmados, congelados y con ubicación de almacén designada.',
    )
    proyecto_location_id = fields.Many2one(
        'stock.location',
        string='Ubicación de Obra',
        related='proyecto_id.location_id',
        readonly=True,
        store=True,
        help='Ubicación física designada para este proyecto en almacén.',
    )

    @api.constrains('proyecto_id')
    def _check_proyecto_elegibilidad(self):
        """Valida que el proyecto cumpla con los candados de congelado y ubicación de almacén."""
        for rec in self:
            if not rec.proyecto_id:
                continue

            proy = rec.proyecto_id
            congelado_ok = (
                bool(proy.baseline_revision_id)
                and proy.baseline_revision_id.state in ('aprobada', 'sustituida')
                and bool(proy.baseline_revision_id.snapshot_capturado)
            )
            if not congelado_ok:
                raise ValidationError(_(
                    'No se puede vincular el proyecto "%s" porque no cuenta con una '
                    'línea base aprobada y congelada.'
                ) % proy.display_name)

            if not proy.location_id:
                raise ValidationError(_(
                    'No se puede vincular el proyecto "%s" porque no cuenta con una '
                    'ubicación de almacén vinculada (location_id). Por favor, asigna o crea '
                    'la ubicación física del proyecto antes de vincular requisiciones.'
                ) % proy.display_name)

            if proy.state == 'cerrado':
                raise ValidationError(_(
                    'No se puede vincular el proyecto "%s" porque se encuentra en estado cerrado.'
                ) % proy.display_name)

    @api.onchange('proyecto_id')
    def _onchange_proyecto_id(self):
        """Pre-puebla el almacén y valida las líneas preexistentes."""
        if not self.proyecto_id:
            return

        # Pre-poblar almacén desde la infraestructura del proyecto
        almacen = self.proyecto_id.warehouse_id
        if not almacen and self.proyecto_id.location_id:
            almacen = self.env['stock.warehouse'].search([
                ('company_id', '=', self.proyecto_id.company_id.id),
                ('view_location_id', 'parent_of', self.proyecto_id.location_id.id),
            ], limit=1)

        if not almacen:
            almacen = self.env['stock.warehouse'].search([
                ('company_id', '=', self.proyecto_id.company_id.id)
            ], limit=1)

        if almacen:
            self.warehouse_id = almacen

        # Si ya había líneas asignadas a otro proyecto, limpiar el vínculo de partida_line_id
        for line in self.line_ids:
            if line.partida_line_id and line.partida_line_id.partida_id.proyecto_id != self.proyecto_id:
                line.partida_line_id = False
