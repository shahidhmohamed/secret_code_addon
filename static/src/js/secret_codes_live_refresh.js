/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { onWillDestroy } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

const TARGET_MODELS = new Set([
    "secret_code_log",
    "secret_codes",
    "product_offer_lead",
]);

patch(ListController.prototype, {
    setup() {
        super.setup();
        this.actionService = useService("action");
        this.busService = useService("bus_service");
        this._secretCodesChannel = "secret_codes_refresh";
        this._secretCodesDestroyed = false;
        this._secretCodesReloading = false;
        this._secretCodesHandler = async (payload) => {
            if (this._secretCodesDestroyed || this._secretCodesReloading) {
                return;
            }
            const modelName = payload?.model || payload?.model_name;
            if (modelName && !TARGET_MODELS.has(modelName)) {
                return;
            }
            if (modelName && this.props?.resModel !== modelName) {
                return;
            }
            this._secretCodesReloading = true;
            try {
                if (this._secretCodesDestroyed) {
                    return;
                }
                if (this.model?.root?.load) {
                    await this.model.root.load();
                    return;
                }
                const controllerId = this.actionService.currentController?.jsId;
                if (controllerId) {
                    await this.actionService.restore(controllerId);
                }
            } finally {
                this._secretCodesReloading = false;
            }
        };
        this.busService.addChannel(this._secretCodesChannel);
        this.busService.subscribe("secret_codes_refresh", this._secretCodesHandler);

        onWillDestroy(() => {
            this._secretCodesDestroyed = true;
            this.busService.deleteChannel(this._secretCodesChannel);
        });
    },
});
