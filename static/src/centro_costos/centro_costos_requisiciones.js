/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ProjectWorkspaceNavigation } from "@gio/dashboard/project_workspace_navigation";

export class CentroCostosRequisiciones extends Component {
    static template = "gio_requisitions.CentroCostosRequisiciones";
    static components = { ProjectWorkspaceNavigation };
    static props = { action: { type: Object, optional: true }, "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            data: null,
            loading: true,
            error: false,
            busy: false,
            filtros: { buscar: "", estado: "", desde: "", hasta: "" },
            pagina: 0,
        });
        this.destroyed = false;
        onWillUnmount(() => { this.destroyed = true; });
        onWillStart(() => this.load(0));
    }

    get projectId() {
        return this.props.action?.context?.active_id
            || this.props.action?.context?.project_id
            || this.props.action?.context?.default_proyecto_id;
    }

    get initialMainTab() {
        return "centro_costos";
    }

    get initialSubTab() {
        return "requisiciones";
    }

    get contexto() {
        return {
            ...this.props.action?.context,
            active_id: this.projectId,
            active_model: "contractor.proyecto",
            project_id: this.projectId,
            default_proyecto_id: this.projectId,
            persistent_project_navigation: true,
            apu_workspace: "requisiciones",
            centro_costos_tipo: "requisiciones",
        };
    }

    get hayFiltros() {
        const { buscar, estado, desde, hasta } = this.state.filtros;
        return Boolean(buscar || estado || desde || hasta);
    }

    get desdeFila() {
        if (!this.state.data?.total) return 0;
        return this.state.pagina * (this.state.data.tamano || 30) + 1;
    }

    get hastaFila() {
        if (!this.state.data?.total) return 0;
        return Math.min(
            (this.state.pagina + 1) * (this.state.data.tamano || 30),
            this.state.data.total
        );
    }

    async load(pagina = 0) {
        if (!this.projectId) {
            this.state.loading = false;
            this.state.error = "No se especificó un proyecto activo.";
            return;
        }
        this.state.loading = true;
        this.state.error = false;
        this.state.pagina = pagina;
        try {
            const data = await this.orm.call(
                "contractor.proyecto",
                "retrieve_centro_costos_requisiciones",
                [[this.projectId], { ...this.state.filtros }, pagina],
                { context: this.contexto }
            );
            if (this.destroyed) return;
            this.state.data = data;
        } catch (error) {
            console.error("[CentroCostosRequisiciones] Error loading data:", error);
            this.state.error = error?.data?.message || error?.message || "No se pudo cargar la información de requisiciones.";
        } finally {
            this.state.loading = false;
        }
    }

    async buscar(ev) {
        if (ev) ev.preventDefault();
        await this.load(0);
    }

    async limpiar() {
        this.state.filtros.buscar = "";
        this.state.filtros.estado = "";
        this.state.filtros.desde = "";
        this.state.filtros.hasta = "";
        await this.load(0);
    }

    async filtrarPorEstado(estado) {
        if (this.state.filtros.estado === estado) {
            this.state.filtros.estado = "";
        } else {
            this.state.filtros.estado = estado;
        }
        await this.load(0);
    }

    async crearRequisicion() {
        if (this.state.busy || !this.projectId) return;
        this.state.busy = true;
        try {
            const action = await this.orm.call(
                "contractor.proyecto",
                "action_open_requisition_wizard",
                [[this.projectId]],
                { context: this.contexto }
            );
            if (action && !action.views) {
                action.views = [[false, "form"]];
            }
            await this.action.doAction(action);
            await this.load(this.state.pagina);
        } catch (error) {
            console.error("[CentroCostosRequisiciones] Error al crear requisición:", error);
            const msg = error?.data?.message || error?.message || "No se pudo iniciar el asistente de requisición.";
            this.notification.add(msg, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    async abrirRequisicion(id) {
        if (!id) return;
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "requisitions",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async abrirAlmacenConfiguracion() {
        if (!this.projectId) return;
        try {
            const action = await this.orm.call(
                "contractor.proyecto",
                "action_open_almacen",
                [[this.projectId]],
                { context: this.contexto }
            );
            await this.action.doAction(action);
        } catch (error) {
            console.error("[CentroCostosRequisiciones] Error al abrir Almacén:", error);
            this.notification.add("No se pudo navegar a la configuración de almacén.", { type: "danger" });
        }
    }

    badgeEstadoClass(estado) {
        const clases = {
            draft: "text-bg-info",
            to_approve: "text-bg-warning",
            approved: "text-bg-primary",
            in_progress: "text-bg-primary",
            partially_done: "text-bg-warning",
            done: "text-bg-success",
            cancel: "text-bg-secondary",
            rejected: "text-bg-danger",
        };
        return clases[estado] || "text-bg-secondary";
    }
}

registry.category("actions").add("gio_centro_costos_requisiciones", CentroCostosRequisiciones);
