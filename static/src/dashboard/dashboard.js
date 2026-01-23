/** @odoo-module */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
const { Component, onWillStart, useState } = owl;

import { KpiCard } from "../components/kpi_card/kpi_card";
import { ChartRenderer } from "../components/chart_renderer/chart_renderer";
import { MapCard } from "../components/map_card/map_card";

export class SecretCodesDashboard extends Component {
  setup() {
    this.orm = useService("orm");
    this.state = useState({
      total_codes: 0,
      total_active: 0,
      total_inactive: 0,
      total_validated: 0,
      total_pending: 0,
      total_success: 0,
      total_fail: 0,
      total_offer_leads: 0,
      total_logs: 0,
      total_validated_logs: 0,
      total_rejected_logs: 0,
      total_pending_logs: 0,
      map_points: [],
    });

    onWillStart(async () => {
      const data = await this.orm.call(
        "secret_codes.dashboard",
        "get_metrics",
        [],
      );
      Object.assign(this.state, data);
      // console.log("Secret Codes dashboard map_points", data.map_points);
    });
  }
}

SecretCodesDashboard.template = "secret_codes.Dashboard";
SecretCodesDashboard.components = { KpiCard, ChartRenderer, MapCard };

registry
  .category("actions")
  .add("secret_codes.dashboard", SecretCodesDashboard);
