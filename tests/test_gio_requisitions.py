# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import common, tagged

from odoo.addons.gio.models.contractor_proyecto_revision import MARCADOR_REVISION_INTERNA


@tagged('post_install', '-at_install', 'gio_requisitions')
class TestGioRequisitions(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Warehouse = cls.env['stock.warehouse']
        cls.Location = cls.env['stock.location']
        cls.Product = cls.env['product.product']
        cls.Proyecto = cls.env['contractor.proyecto']
        cls.Partida = cls.env['contractor.partida']
        cls.PartidaLine = cls.env['contractor.partida.line']
        cls.Requisition = cls.env['requisitions']

        cls.warehouse = cls.Warehouse.search([('company_id', '=', cls.company.id)], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.Warehouse.create({
                'name': 'Almacén Test GIO Requisitions',
                'code': 'WH_GIOR',
                'company_id': cls.company.id,
            })

        cls.employee = cls.env['hr.employee'].create({
            'name': 'Residente de Obra Test',
            'company_id': cls.company.id,
        })

        cls.product = cls.Product.create({
            'name': 'Cemento Gris 50kg Test',
            'type': 'consu',
            'uom_id': cls.env.ref('uom.product_uom_unit').id,
        })

        cls.jornada = cls.env['contractor.jornada.trabajo'].create({
            'code': 'JT-TEST-GIOR',
            'name': 'Jornada Test Requisitions',
        })

        # Ubicación física para pruebas
        cls.ubicacion_obra = cls.Location.create({
            'name': 'OBRA-TEST-01',
            'location_id': cls.warehouse.view_location_id.id,
            'usage': 'internal',
            'company_id': cls.company.id,
        })

        cls.env.user.write({
            'group_ids': [(4, cls.env.ref('dh_requisitions.group_requisitions_requester').id)]
        })

    def _crear_proyecto_base(self, congelado=False, con_almacen=False):
        """Helper para inicializar proyectos con diferentes estados de elegibilidad."""
        proyecto = self.Proyecto.create({
            'descripcion': 'Construcción Nave Industrial Alpha',
            'concurso': 'OBRA-ALPHA-2026',
            'jornada_default_id': self.jornada.id,
            'warehouse_id': self.warehouse.id if con_almacen else False,
            'state': 'borrador',
        })

        partida = self.Partida.create({
            'proyecto_id': proyecto.id,
            'clave': 'ESTR-01',
            'descripcion': 'Cimentación y Estructura',
            'cantidad': 1.0,
            'unidad': self.env.ref('uom.product_uom_unit').id,
        })

        linea_insumo = self.PartidaLine.create({
            'partida_id': partida.id,
            'product_id': self.product.id,
            'cantidad': 100.0,
            'tipo_apu': 'material',
            'es_grupo': False,
            'precio': 250.0,
        })

        if con_almacen:
            proyecto.location_id = self.ubicacion_obra.id

        if congelado:
            # Simular baseline aprobada y congelada
            revision = self.env['contractor.proyecto.revision'].with_context(
                _revision_crear=MARCADOR_REVISION_INTERNA,
            ).create({
                'proyecto_id': proyecto.id,
                'nombre': 'Revisión Baseline Inicial',
                'motivo': 'Aprobación inicial de baseline contractual para pruebas',
            })
            revision.with_context(_revision_lifecycle=MARCADOR_REVISION_INTERNA).write({
                'state': 'aprobada',
                'snapshot_capturado': True,
                'fecha_aprobacion': fields.Datetime.now(),
            })
            proyecto.write({
                'baseline_revision_id': revision.id,
                'revision_actual_id': revision.id,
                'state': 'borrador',
            })

        return proyecto, linea_insumo

    def test_01_candado_proyecto_sin_congelar(self):
        """Valida que un proyecto sin congelar rechace la creación y vinculación de requisiciones."""
        proy_borrador, _ = self._crear_proyecto_base(congelado=False, con_almacen=True)
        self.assertFalse(proy_borrador.is_requisition_eligible)

        # 1. No debe permitir crear requisición manual vinculada a este proyecto
        with self.assertRaises(ValidationError):
            self.Requisition.create({
                'employee_id': self.employee.id,
                'warehouse_id': self.warehouse.id,
                'user_id': self.env.user.id,
                'proyecto_id': proy_borrador.id,
                'date_required': fields.Date.today(),
            })

        # 2. No debe permitir abrir el asistente desde el proyecto
        with self.assertRaises(UserError):
            proy_borrador.action_open_requisition_wizard()

    def test_02_candado_proyecto_sin_ubicacion_almacen(self):
        """Valida que un proyecto congelado pero sin location_id asignado rechace requisiciones."""
        proy_sin_almacen, _ = self._crear_proyecto_base(congelado=True, con_almacen=False)
        self.assertFalse(proy_sin_almacen.is_requisition_eligible)

        # 1. No debe permitir vincular requisición
        with self.assertRaises(ValidationError):
            self.Requisition.create({
                'employee_id': self.employee.id,
                'warehouse_id': self.warehouse.id,
                'user_id': self.env.user.id,
                'proyecto_id': proy_sin_almacen.id,
                'date_required': fields.Date.today(),
            })

        # 2. No debe permitir abrir wizard
        with self.assertRaises(UserError):
            proy_sin_almacen.action_open_requisition_wizard()

    def test_03_proyecto_elegible_y_onchange_almacen(self):
        """Valida que un proyecto con baseline aprobada y con ubicación sea elegible y pre-pueble almacén."""
        proy_ok, _ = self._crear_proyecto_base(congelado=True, con_almacen=True)
        self.assertEqual(proy_ok.state, 'borrador')
        self.assertTrue(proy_ok.is_requisition_eligible)

        req = self.Requisition.new({
            'employee_id': self.employee.id,
            'user_id': self.env.user.id,
            'proyecto_id': proy_ok.id,
            'date_required': fields.Date.today(),
        })
        req._onchange_proyecto_id()
        self.assertEqual(req.warehouse_id, self.warehouse)

        # Validar que si el proyecto pasa a cerrado, se rechacen las requisiciones
        proy_ok.state = 'cerrado'
        self.assertFalse(proy_ok.is_requisition_eligible)
        with self.assertRaises(UserError):
            proy_ok.action_open_requisition_wizard()
        with self.assertRaises(ValidationError):
            self.Requisition.create({
                'employee_id': self.employee.id,
                'warehouse_id': self.warehouse.id,
                'user_id': self.env.user.id,
                'proyecto_id': proy_ok.id,
                'date_required': fields.Date.today(),
            })
        proy_ok.state = 'borrador'
        self.assertTrue(proy_ok.is_requisition_eligible)

    def test_04_wizard_creacion_desde_explosion(self):
        """Valida el flujo de generación de requisición a través del wizard de explosión de insumos."""
        proy_ok, linea_insumo = self._crear_proyecto_base(congelado=True, con_almacen=True)

        action_dict = proy_ok.action_open_requisition_wizard()
        wizard_id = action_dict.get('res_id')
        self.assertTrue(wizard_id)

        wizard = self.env['contractor.explosion.requisicion.wizard'].browse(wizard_id)
        self.assertEqual(wizard.proyecto_id, proy_ok)
        self.assertEqual(len(wizard.line_ids), 1)

        w_line = wizard.line_ids[0]
        self.assertEqual(w_line.partida_line_id, linea_insumo)
        self.assertEqual(w_line.cantidad_explosion, 100.0)

        # Asignar cantidad y crear
        w_line.product_qty = 35.0
        wizard.user_id = self.env.user.id
        wizard.employee_id = self.employee.id

        res_action = wizard.action_crear_requisicion()
        req_id = res_action.get('res_id')
        self.assertTrue(req_id)

        nueva_req = self.Requisition.browse(req_id)
        self.assertEqual(nueva_req.proyecto_id, proy_ok)
        self.assertEqual(nueva_req.state, 'draft')
        self.assertEqual(len(nueva_req.line_ids), 1)

        req_line = nueva_req.line_ids[0]
        self.assertEqual(req_line.partida_line_id, linea_insumo)
        self.assertEqual(req_line.product_id, self.product)
        self.assertEqual(req_line.product_qty, 35.0)

    def test_05_trazabilidad_pasiva_en_explosion(self):
        """Valida que la explosión de GIO refleje en tiempo real lo requisitado y suministrado."""
        proy_ok, linea_insumo = self._crear_proyecto_base(congelado=True, con_almacen=True)

        # Crear requisición vinculada
        req = self.Requisition.create({
            'employee_id': self.employee.id,
            'user_id': self.env.user.id,
            'warehouse_id': self.warehouse.id,
            'proyecto_id': proy_ok.id,
            'date_required': fields.Date.today(),
            'state': 'draft',
            'line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_qty': 40.0,
                    'partida_line_id': linea_insumo.id,
                    'line_type': 'material',
                })
            ]
        })

        linea_insumo.invalidate_recordset(['qty_requisited', 'qty_supplied', 'qty_in_transit'])
        self.assertEqual(linea_insumo.qty_requisited, 40.0)
        self.assertEqual(linea_insumo.qty_in_transit, 40.0)
        self.assertEqual(linea_insumo.qty_supplied, 0.0)

        # Simular entrega de material en la requisición (qty_done)
        req_line = req.line_ids[0]
        req_line.qty_done = 15.0

        linea_insumo.invalidate_recordset(['qty_requisited', 'qty_supplied', 'qty_in_transit'])
        self.assertEqual(linea_insumo.qty_supplied, 15.0)
        self.assertEqual(linea_insumo.qty_in_transit, 25.0)

    def test_06_dashboard_rpc_retrieve(self):
        """Valida el método retrieve_centro_costos_requisiciones para el dashboard de GIO."""
        proy_ok, linea_insumo = self._crear_proyecto_base(congelado=True, con_almacen=True)

        self.Requisition.create({
            'employee_id': self.employee.id,
            'user_id': self.env.user.id,
            'warehouse_id': self.warehouse.id,
            'proyecto_id': proy_ok.id,
            'date_required': fields.Date.today(),
            'state': 'draft',
            'line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_qty': 20.0,
                    'partida_line_id': linea_insumo.id,
                    'line_type': 'material',
                })
            ]
        })

        datos = proy_ok.retrieve_centro_costos_requisiciones()
        self.assertTrue(datos['configurado_almacen'])
        self.assertTrue(datos['congelado'])
        self.assertTrue(datos['elegible'])
        self.assertEqual(datos['total'], 1)
        self.assertEqual(len(datos['filas']), 1)
        self.assertEqual(datos['conteo_estados']['total'], 1)
        self.assertEqual(datos['kpis_insumos']['total_presupuesto'], 100.0)
        self.assertEqual(datos['kpis_insumos']['total_requisitado'], 20.0)

    def test_07_bloqueo_presupuestal_wizard(self):
        """Valida que no se permita solicitar más cantidad de la planeada en la explosión (Punto 4)."""
        proy_ok, linea_insumo = self._crear_proyecto_base(congelado=True, con_almacen=True)
        # Presupuesto: 100.0
        action = proy_ok.action_open_requisition_wizard()
        wizard = self.env['contractor.explosion.requisicion.wizard'].browse(action['res_id'])
        wizard.user_id = self.env.user.id
        wizard.employee_id = self.employee.id

        w_line = wizard.line_ids[0]
        self.assertEqual(w_line.qty_disponible_planeada, 100.0)

        # Intentar solicitar 150.0 (excede los 100.0 disponibles)
        w_line.product_qty = 150.0
        with self.assertRaises(UserError):
            wizard.action_crear_requisicion()

        # Solicitar 60.0 es válido
        w_line.product_qty = 60.0
        res = wizard.action_crear_requisicion()
        self.assertTrue(res.get('res_id'))

        # Ahora el disponible restante debe ser 40.0
        linea_insumo.invalidate_recordset(['qty_requisited'])
        self.assertEqual(linea_insumo.qty_requisited, 60.0)
        action2 = proy_ok.action_open_requisition_wizard()
        wizard2 = self.env['contractor.explosion.requisicion.wizard'].browse(action2['res_id'])
        w_line2 = wizard2.line_ids[0]
        self.assertEqual(w_line2.qty_disponible_planeada, 40.0)

        # Intentar solicitar 50.0 debe fallar porque solo quedan 40.0
        w_line2.product_qty = 50.0
        wizard2.user_id = self.env.user.id
        wizard2.employee_id = self.employee.id
        with self.assertRaises(UserError):
            wizard2.action_crear_requisicion()

    def test_08_fallback_categoria_requisicion(self):
        """Valida que productos con categorías sin configuración previa reciban fallback automático (Punto 7)."""
        # Crear categoría sin requisition_type y sin allow_requisition
        categ_sin_config = self.env['product.category'].create({
            'name': 'Materiales Obra Especial Sin Config',
        })
        self.assertFalse(categ_sin_config.requisition_type)
        self.assertFalse(categ_sin_config.allow_requisition)

        prod_sin_config = self.Product.create({
            'name': 'Grava Triturada Especial',
            'type': 'consu',
            'categ_id': categ_sin_config.id,
            'uom_id': self.env.ref('uom.product_uom_unit').id,
        })

        # Crear el proyecto sin congelar aún para poder agregar el insumo
        proy_ok, linea_insumo = self._crear_proyecto_base(congelado=False, con_almacen=True)
        partida = linea_insumo.partida_id
        linea_insumo2 = self.PartidaLine.create({
            'partida_id': partida.id,
            'product_id': prod_sin_config.id,
            'cantidad': 50.0,
            'tipo_apu': 'material',
            'es_grupo': False,
            'precio': 120.0,
        })

        # Congelar revisión contractual
        revision = self.env['contractor.proyecto.revision'].with_context(
            _revision_crear=MARCADOR_REVISION_INTERNA,
        ).create({
            'proyecto_id': proy_ok.id,
            'nombre': 'Revisión Baseline Inicial Test 08',
            'motivo': 'Aprobación inicial de baseline contractual para pruebas',
        })
        revision.with_context(_revision_lifecycle=MARCADOR_REVISION_INTERNA).write({
            'state': 'aprobada',
            'snapshot_capturado': True,
            'fecha_aprobacion': fields.Datetime.now(),
        })
        proy_ok.write({
            'baseline_revision_id': revision.id,
            'revision_actual_id': revision.id,
            'state': 'borrador',
        })

        # Abrir wizard y solicitar
        action = proy_ok.action_open_requisition_wizard(selected_lines=linea_insumo2)
        wizard = self.env['contractor.explosion.requisicion.wizard'].browse(action['res_id'])
        wizard.user_id = self.env.user.id
        wizard.employee_id = self.employee.id
        wizard.line_ids[0].product_qty = 20.0

        res = wizard.action_crear_requisicion()
        req = self.Requisition.browse(res['res_id'])

        # Verificar que la categoría del producto fue configurada automáticamente por fallback
        self.assertTrue(categ_sin_config.allow_requisition)
        self.assertEqual(categ_sin_config.requisition_type, 'material')
        self.assertEqual(req.line_ids[0].line_type, 'material')

    def test_09_metricas_productos_solicitados_surtidos_y_excedente(self):
        """Valida las métricas de productos únicos solicitados vs surtidos y detección de excedente (Puntos 3 y 5)."""
        proy_ok, linea1 = self._crear_proyecto_base(congelado=True, con_almacen=True)
        # Presupuesto linea1: 100.0 de self.product

        # Requisitar 50.0 del producto 1
        req1 = self.Requisition.create({
            'employee_id': self.employee.id,
            'user_id': self.env.user.id,
            'warehouse_id': self.warehouse.id,
            'proyecto_id': proy_ok.id,
            'date_required': fields.Date.today(),
            'state': 'draft',
            'line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'product_qty': 50.0,
                    'partida_line_id': linea1.id,
                    'line_type': 'material',
                })
            ]
        })

        datos = proy_ok.retrieve_centro_costos_requisiciones()
        kpis = datos['kpis_insumos']
        self.assertEqual(kpis['total_productos_solicitados'], 1)
        self.assertEqual(kpis['total_productos_surtidos'], 0)
        self.assertFalse(kpis['hay_excedente_requisitado'])

        # Surtir completamente los 50.0 solicitados
        req1.line_ids[0].qty_done = 50.0
        datos_surtido = proy_ok.retrieve_centro_costos_requisiciones()
        kpis_surtido = datos_surtido['kpis_insumos']
        self.assertEqual(kpis_surtido['total_productos_solicitados'], 1)
        self.assertEqual(kpis_surtido['total_productos_surtidos'], 1)

    def test_10_bloqueo_duplicar_ubicacion_almacen(self):
        """Valida que no se permita crear una ubicación si el proyecto ya tiene una (Punto 6)."""
        proy_ok, _ = self._crear_proyecto_base(congelado=True, con_almacen=True)
        self.assertTrue(proy_ok.location_id)

        with self.assertRaises(UserError):
            proy_ok.action_crear_ubicacion_proyecto()

    def test_11_gio_user_without_requisitions_permission(self):
        """Valida que un usuario de GIO sin permisos de requisiciones pueda navegar el proyecto sin AccessError, pero no crear requisiciones."""
        user_gio = self.env['res.users'].create({
            'name': 'Planeador GIO Test',
            'login': 'planeador_gio_test@example.com',
            'company_id': self.company.id,
            'company_ids': [(6, 0, [self.company.id])],
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('gio.group_gio_planeador').id,
            ])],
        })
        proy_ok, _ = self._crear_proyecto_base(congelado=True, con_almacen=True)

        # 1. El usuario de GIO puede consultar el proyecto y sus partidas sin AccessError
        proy_leido = proy_ok.with_user(user_gio)
        self.assertEqual(proy_leido.requisition_count, 0)

        # 2. Si intenta solicitar requisición, debe recibir UserError explicativo en vez de AccessError abrupto
        with self.assertRaises(UserError):
            proy_leido.action_open_requisition_wizard()

    def test_12_alerta_informativa_excedente_apu_sin_bloqueo(self):
        """Valida que una requisición con cantidad superior a la explosión APU marque excedente y notifique sin bloquear (H-10)."""
        proy_ok, linea_insumo = self._crear_proyecto_base(congelado=True, con_almacen=True)
        # La explosión tiene 100.0 unidades (10 * 10)
        self.assertEqual(linea_insumo.cantidad_explosion, 100.0)

        # Crear requisición solicitando 120.0 unidades (20.0 de excedente)
        req = self.Requisition.create({
            'employee_id': self.employee.id,
            'proyecto_id': proy_ok.id,
            'warehouse_id': proy_ok.warehouse_id.id,
            'user_id': self.env.user.id,
            'line_ids': [(0, 0, {
                'partida_line_id': linea_insumo.id,
                'product_id': self.product.id,
                'product_qty': 120.0,
                'line_type': 'material',
            })]
        })

        line = req.line_ids[0]
        self.assertTrue(line.is_excedente_apu)
        self.assertEqual(line.qty_excedente_apu, 20.0)

        # Debe permitir confirmar sin lanzar ValidationError
        req.action_confirm()
        self.assertEqual(req.state, 'to_approve')

