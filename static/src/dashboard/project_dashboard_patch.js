/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProjectDashboard } from "@gio/dashboard/project_dashboard";

patch(ProjectDashboard.prototype, {
    normalizeWorkspace(workspace) {
        if (workspace === "requisiciones") {
            return "requisiciones";
        }
        return super.normalizeWorkspace(workspace);
    },

    syncTabsFromWorkspace(workspace) {
        if (workspace === "requisiciones") {
            this.state.mainTab = "centro_costos";
            this.state.subTab = "requisiciones";
            return;
        }
        return super.syncTabsFromWorkspace(workspace);
    },

    getSubTabs() {
        const subs = super.getSubTabs();
        if (this.state.mainTab === "centro_costos") {
            return (subs || []).map((sub) => {
                if (sub.key === "requisiciones") {
                    return {
                        key: "requisiciones",
                        label: "Requisiciones",
                        workspace: "requisiciones",
                        placeholder: false,
                        historical: false,
                    };
                }
                return sub;
            });
        }
        return subs;
    },

    async openWorkspace(workspace) {
        if (workspace === "requisiciones") {
            const ctx = this.getActionContext();
            const projectId = this.getProjectId(ctx) || this.state.data.id;
            if (!projectId) {
                return;
            }
            try {
                const action = await this.orm.call(
                    "contractor.proyecto",
                    "action_open_requisiciones",
                    [projectId],
                    { context: ctx }
                );
                await this.action.doAction(action, {
                    stackPosition: "replaceCurrentAction",
                });
            } catch (error) {
                console.error("[ProjectDashboardPatch] Error al abrir Requisiciones:", error);
                this.notification.add("No se pudo abrir el espacio de Requisiciones.", { type: "danger" });
            }
            return;
        }
        return super.openWorkspace(workspace);
    },
});
