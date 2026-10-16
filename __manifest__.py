# -*- coding: utf-8 -*-
{
    "name": "Conector: GIO y Requisiciones",
    "version": "19.0.1.1.0",
    "category": "Supply Chain / Construction",
    "summary": "Vinculación entre proyectos de obra GIO y requisiciones de materiales.",
    "description": """
Conector: GIO y Requisiciones
=============================
Permite generar y dar seguimiento a las requisiciones de insumos directamente desde los proyectos y presupuestos de obra en GIO.

Características principales:
- Creación de requisiciones a partir de la explosión de insumos del proyecto.
- Validación de que el proyecto cuente con almacén asignado y presupuesto aprobado.
- Consulta del avance de suministro y materiales solicitados en el panel del proyecto.
    """,
    "author": "Aldahir / GIO Architect",
    "maintainer": "Aldahir",
    "website": "https://github.com/dovahir/supply_chain_aio.git",
    "license": "LGPL-3",
    "depends": [
        "base",
        "stock",
        "supply_chain_aio",
        "dh_requisitions",
        "gio",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/contractor_explosion_requisicion_wizard_views.xml",
        "views/contractor_partida_line_views.xml",
        "views/contractor_proyecto_views.xml",
        "views/requisitions_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "gio_requisitions/static/src/dashboard/project_dashboard_patch.js",
            "gio_requisitions/static/src/dashboard/project_dashboard_patch.xml",
            "gio_requisitions/static/src/centro_costos/centro_costos_requisiciones.js",
            "gio_requisitions/static/src/centro_costos/centro_costos_requisiciones.xml",
            "gio_requisitions/static/src/centro_costos/centro_costos_requisiciones.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
