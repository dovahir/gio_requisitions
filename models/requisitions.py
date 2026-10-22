# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from markupsafe import Markup, escape


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

    def action_confirm(self):
        res = super().action_confirm()
        for rec in self:
            excedentes = rec.line_ids.filtered(lambda l: getattr(l, 'is_excedente_apu', False))
            if excedentes:
                detalles = []
                for l in excedentes:
                    partida_label = l.partida_id.display_name if l.partida_id else ''
                    detalles.append(
                        "<li><strong>%s</strong> (Partida: %s): Requisitado <strong>%s %s</strong> vs Explosión APU <strong>%s %s</strong> (Excedente: <strong>+%s %s</strong>)</li>" % (
                            escape(l.product_id.display_name),
                            escape(partida_label),
                            l.product_qty,
                            escape(l.product_uom_id.name or ''),
                            l.partida_line_id.cantidad_explosion,
                            escape(l.product_uom_id.name or ''),
                            l.qty_excedente_apu,
                            escape(l.product_uom_id.name or '')
                        )
                    )
                body = Markup(
                    "<div class='alert alert-warning mb-0'>"
                    "<strong>%s</strong><br/>"
                    "%s"
                    "<ul>%s</ul>"
                    "</div>"
                ) % (
                    _("Aviso Presupuestal de Obra: Excedente APU Solicitado"),
                    _("La requisición incluye cantidades que exceden la explosión presupuestal del APU del proyecto:"),
                    Markup("".join(detalles))
                )
                rec.message_post(body=body, subtype_xmlid="mail.mt_note")
        return res
