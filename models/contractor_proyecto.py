# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ContractorProyecto(models.Model):
    _inherit = 'contractor.proyecto'

    is_requisition_eligible = fields.Boolean(
        string='Elegible para Requisiciones',
        compute='_compute_is_requisition_eligible',
        store=True,
        index=True,
        help='Indica si el proyecto cumple con los candados contractuales: '
             'línea base aprobada/congelada, estado activo/en preparación y '
             'ubicación física de almacén asignada.',
    )
    requisition_ids = fields.One2many(
        'requisitions',
        'proyecto_id',
        string='Requisiciones',
    )
    requisition_count = fields.Integer(
        string='Total Requisiciones',
        compute='_compute_requisition_count',
    )

    @api.depends(
        'baseline_revision_id',
        'baseline_revision_id.state',
        'baseline_revision_id.snapshot_capturado',
        'state',
        'location_id'
    )
    def _compute_is_requisition_eligible(self):
        for rec in self:
            congelado_ok = (
                bool(rec.baseline_revision_id)
                and rec.baseline_revision_id.state in ('aprobada', 'sustituida')
                and bool(rec.baseline_revision_id.snapshot_capturado)
            )
            estado_ok = rec.state != 'cerrado'
            almacen_ok = bool(rec.location_id)
            rec.is_requisition_eligible = bool(congelado_ok and estado_ok and almacen_ok)

    @api.depends('requisition_ids')
    def _compute_requisition_count(self):
        for rec in self:
            rec.requisition_count = len(rec.sudo().requisition_ids)

    def _validar_elegibilidad_requisiciones(self):
        """Verifica los candados obligatorios antes de permitir operaciones de requisición."""
        self.ensure_one()
        self.check_access('read')
        congelado_ok = (
            bool(self.baseline_revision_id)
            and self.baseline_revision_id.state in ('aprobada', 'sustituida')
            and bool(self.baseline_revision_id.snapshot_capturado)
        )
        if not congelado_ok:
            raise UserError(_(
                'El proyecto "%s" no cuenta con una línea base aprobada y congelada. '
                'Debe aprobar y congelar una revisión antes de solicitar insumos.'
            ) % self.display_name)

        if not self.location_id:
            raise UserError(_(
                'El proyecto "%s" no cuenta con una ubicación de almacén vinculada. '
                'Por favor, asigna o crea la ubicación física en la pestaña "Almacén" '
                'antes de generar requisiciones.'
            ) % self.display_name)

        if self.state == 'cerrado':
            raise UserError(_(
                'El proyecto "%s" se encuentra cerrado. No se permiten '
                'requisiciones en proyectos cerrados.'
            ) % self.display_name)

    def action_crear_ubicacion_proyecto(self):
        """Impide duplicar la ubicación de almacén si el proyecto ya tiene una asignada."""
        self.ensure_one()
        if self.location_id:
            raise UserError(_(
                'El proyecto "%s" ya cuenta con una ubicación de almacén asignada: %s. '
                'No es posible crear una nueva ubicación.'
            ) % (self.display_name, self.location_id.complete_name))
        return super().action_crear_ubicacion_proyecto()

    def action_open_requisition_wizard(self, selected_lines=None):
        """Abre el asistente de creación de requisiciones precargado con el proyecto."""
        self.ensure_one()
        puede_solicitar = (
            self.env.is_admin()
            or self.env.user.has_group('gio.group_gio_planeador')
            or self.env.user.has_group('dh_requisitions.group_requisitions_requester')
        )
        if not puede_solicitar:
            raise UserError(_("Para solicitar requisiciones desde el proyecto, debes contar con el perfil de Planeador de Obra o Solicitante de Requisiciones."))
        self._validar_elegibilidad_requisiciones()

        # Determinar almacén por defecto desde el proyecto o su ubicación
        almacen_id = self.warehouse_id.id if self.warehouse_id else False
        if not almacen_id and self.location_id:
            wh = self.env['stock.warehouse'].search([
                ('company_id', '=', self.company_id.id),
                ('view_location_id', 'parent_of', self.location_id.id),
            ], limit=1)
            almacen_id = wh.id if wh else False

        # Insumos elegibles de la explosión (partidas hijas con insumos)
        if selected_lines:
            lineas_explosion = selected_lines.filtered(
                lambda l: l.partida_id.proyecto_id.id == self.id and not l.es_grupo and l.product_id
            )
        else:
            lineas_explosion = self.env['contractor.partida.line'].search([
                ('partida_id.proyecto_id', '=', self.id),
                ('es_grupo', '=', False),
                ('product_id', '!=', False),
            ])

        lineas_wizard = []
        for line in lineas_explosion:
            presupuesto = line.cantidad_explosion
            lineas_wizard.append((0, 0, {
                'partida_line_id': line.id,
                'product_id': line.product_id.id,
                'cantidad_explosion': presupuesto,
                'qty_requisited': line.qty_requisited,
                'product_qty': 0.0,
            }))

        wizard = self.env['contractor.explosion.requisicion.wizard'].create({
            'proyecto_id': self.id,
            'warehouse_id': almacen_id,
            'company_id': self.company_id.id,
            'date_required': fields.Date.context_today(self),
            'line_ids': lineas_wizard,
        })

        return {
            'name': _('Generar Requisición desde Explosión: %s') % self.display_name,
            'type': 'ir.actions.act_window',
            'res_model': 'contractor.explosion.requisicion.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
        }

    def action_open_requisiciones(self):
        """Abre el espacio de trabajo de Requisiciones en Centro de Costos."""
        self.ensure_one()
        contexto = {}
        if hasattr(self, '_contexto_workspace'):
            contexto = self._contexto_workspace(
                'requisiciones',
                active_id=self.id,
                active_model=self._name,
                centro_costos_tipo='requisiciones'
            )
        else:
            contexto = {
                'active_id': self.id,
                'active_model': self._name,
                'project_id': self.id,
                'default_proyecto_id': self.id,
                'apu_workspace': 'requisiciones',
                'centro_costos_tipo': 'requisiciones',
            }

        return {
            'type': 'ir.actions.client',
            'name': _('Requisiciones'),
            'tag': 'gio_centro_costos_requisiciones',
            'context': contexto,
        }

    def action_view_requisitions(self):
        """Abre la vista estándar de requisiciones filtradas por este proyecto (Smart Button)."""
        self.ensure_one()
        self.check_access('read')
        puede_ver = (
            self.env.is_admin()
            or self.env.user.has_group('gio.group_gio_consulta')
            or self.env.user.has_group('dh_requisitions.group_requisitions_requester')
        )
        if not puede_ver:
            raise UserError(_("No cuentas con permisos para acceder a las requisiciones del proyecto."))
        action = self.env.ref('dh_requisitions.requisitions_action_all').read()[0]
        action['domain'] = [('proyecto_id', '=', self.id)]
        action['context'] = {
            'default_proyecto_id': self.id,
            'search_default_proyecto_id': self.id,
        }
        return action

    def retrieve_centro_costos_requisiciones(self, filtros=None, pagina=0):
        """Método RPC para el Dashboard de Requisiciones en GIO Centro de Costos."""
        self.ensure_one()
        self.check_access('read')
        filtros = filtros or {}
        if not isinstance(filtros, dict):
            raise ValidationError(_('Los filtros deben ser un objeto.'))

        Requisition = self.env['requisitions'].with_company(self.company_id)
        PartidaLine = self.env['contractor.partida.line'].with_company(self.company_id)

        # 1. Metadatos de configuración
        configurado_almacen = bool(self.location_id)
        congelado_ok = (
            bool(self.baseline_revision_id)
            and self.baseline_revision_id.state in ('aprobada', 'sustituida')
            and bool(self.baseline_revision_id.snapshot_capturado)
        )
        try:
            Requisition.check_access('read')
        except Exception:
            return {
                'filas': [],
                'total_filas': 0,
                'total_paginas': 0,
                'pagina_actual': 0,
                'puede_crear': False,
                'configurado_almacen': configurado_almacen,
                'congelado_ok': congelado_ok,
                'kpis': {'total_requisiciones': 0, 'aprobadas': 0, 'en_proceso': 0, 'finalizadas': 0},
            }

        puede_crear = self.is_requisition_eligible and (
            self.env.is_admin()
            or self.env.user.has_group('gio.group_gio_planeador')
            or self.env.user.has_group('dh_requisitions.group_requisitions_requester')
        )

        # 2. Dominio base
        domain = [('proyecto_id', '=', self.id)]
        if filtros.get('buscar'):
            termino = filtros['buscar'].strip()
            domain += ['|', '|',
                       ('name', 'ilike', termino),
                       ('employee_id.name', 'ilike', termino),
                       ('user_id.name', 'ilike', termino)]
        if filtros.get('estado'):
            domain += [('state', '=', filtros['estado'])]
        if filtros.get('desde'):
            domain += [('date_required', '>=', filtros['desde'])]
        if filtros.get('hasta'):
            domain += [('date_required', '<=', filtros['hasta'])]

        total_reqs = Requisition.search_count(domain)
        tamano_pagina = 30
        offset = max(0, int(pagina)) * tamano_pagina
        reqs = Requisition.search(domain, limit=tamano_pagina, offset=offset, order='date_required desc, id desc')

        # 3. Filas de requisiciones
        filas = []
        estados_dict = dict(Requisition._fields['state']._description_selection(self.env))
        for r in reqs:
            total_items = sum(r.line_ids.mapped('product_qty'))
            total_done = sum(r.line_ids.mapped('qty_done'))
            pct_surtido = (total_done / total_items * 100.0) if total_items > 0 else 0.0

            filas.append({
                'id': r.id,
                'name': r.name,
                'fecha_creacion': str(r.date_created.date()) if r.date_created else '',
                'fecha_requerida': str(r.date_required) if r.date_required else '',
                'solicitante': r.employee_id.name or '',
                'autoriza': r.user_id.name or '',
                'almacen': r.warehouse_id.name or '',
                'estado': r.state,
                'estado_label': estados_dict.get(r.state, r.state),
                'total_lineas': len(r.line_ids),
                'total_items': round(total_items, 2),
                'total_done': round(total_done, 2),
                'pct_surtido': round(pct_surtido, 1),
            })

        # 4. Métricas de Insumos Presupuestados vs Requisitados
        insumos_proyecto = PartidaLine.search([
            ('partida_id.proyecto_id', '=', self.id),
            ('es_grupo', '=', False),
            ('product_id', '!=', False),
        ])
        total_presupuesto = sum(insumos_proyecto.mapped('cantidad_explosion'))
        total_requisitado = sum(insumos_proyecto.mapped('qty_requisited'))
        total_suministrado = sum(insumos_proyecto.mapped('qty_supplied'))
        pct_suministrado_global = (total_suministrado / total_presupuesto * 100.0) if total_presupuesto > 0 else 0.0

        # Excedentes respecto a lo planeado en la explosión de insumos (Punto 5)
        excedente_requisitado = sum(
            max(0.0, line.qty_requisited - line.cantidad_explosion)
            for line in insumos_proyecto
        )
        excedente_suministrado = sum(
            max(0.0, line.qty_supplied - line.cantidad_explosion)
            for line in insumos_proyecto
        )

        # 5. Métricas de Productos Solicitados vs Totalmente Surtidos (Punto 3)
        req_lines = self.env['requisitions.line'].search([
            ('requisition_id.proyecto_id', '=', self.id),
            ('requisition_id.state', 'not in', ('cancel', 'rejected')),
            ('product_id', '!=', False),
        ])
        prod_map = {}
        for rl in req_lines:
            pid = rl.product_id.id
            if pid not in prod_map:
                prod_map[pid] = {'requested': 0.0, 'done': 0.0}
            prod_map[pid]['requested'] += rl.product_qty
            prod_map[pid]['done'] += rl.qty_done

        total_productos_solicitados = len(prod_map)
        total_productos_surtidos = sum(
            1 for p in prod_map.values()
            if p['requested'] > 0 and round(p['done'], 4) >= round(p['requested'], 4)
        )

        # Conteo por estado de todas las requisiciones del proyecto (sin paginación)
        all_reqs = Requisition.search([('proyecto_id', '=', self.id)])
        conteo_estados = {
            'draft': len(all_reqs.filtered(lambda x: x.state == 'draft')),
            'to_approve': len(all_reqs.filtered(lambda x: x.state == 'to_approve')),
            'approved': len(all_reqs.filtered(lambda x: x.state == 'approved')),
            'in_progress': len(all_reqs.filtered(lambda x: x.state in ('in_progress', 'partially_done'))),
            'done': len(all_reqs.filtered(lambda x: x.state == 'done')),
            'cancel': len(all_reqs.filtered(lambda x: x.state in ('cancel', 'rejected'))),
            'total': len(all_reqs),
        }

        return {
            'proyecto': self.concurso or self.descripcion or self.display_name,
            'configurado_almacen': configurado_almacen,
            'ubicacion_almacen': self.location_id.complete_name if self.location_id else '',
            'congelado': congelado_ok,
            'elegible': self.is_requisition_eligible,
            'puede_crear': puede_crear,
            'estados': Requisition._fields['state']._description_selection(self.env),
            'conteo_estados': conteo_estados,
            'kpis_insumos': {
                'total_presupuesto': round(total_presupuesto, 2),
                'total_requisitado': round(total_requisitado, 2),
                'total_suministrado': round(total_suministrado, 2),
                'pct_suministrado': round(pct_suministrado_global, 1),
                'total_productos_solicitados': total_productos_solicitados,
                'total_productos_surtidos': total_productos_surtidos,
                'excedente_requisitado': round(excedente_requisitado, 2),
                'hay_excedente_requisitado': round(excedente_requisitado, 4) > 0,
                'excedente_suministrado': round(excedente_suministrado, 2),
                'hay_excedente_suministrado': round(excedente_suministrado, 4) > 0,
            },
            'filas': filas,
            'total': total_reqs,
            'pagina': pagina,
            'tamano': tamano_pagina,
        }
