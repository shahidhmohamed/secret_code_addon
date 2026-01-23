/** @odoo-module */

import { registry } from "@web/core/registry";
import { loadJS } from "@web/core/assets";
const { Component, onWillStart, useRef, onMounted } = owl;

export class ChartRenderer extends Component {
  setup() {
    this.chartRef = useRef("chart");
    onWillStart(async () => {
      await loadJS(
        "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js",
      );
    });

    onMounted(() => this.renderChart());
  }

  renderChart() {
    const safeNumber = (value) => (Number.isFinite(Number(value)) ? Number(value) : 0);
    const datasetLabel = this.props.title || "Metrics";
    const hasCustomSeries = Array.isArray(this.props.labels) && Array.isArray(this.props.values);
    const defaultLabels = ["Validated", "Rejected", "Pending", "Total"];
    const defaultValues = [
      this.props.success,
      this.props.cancelled,
      this.props.open,
      this.props.all,
    ];
    const labels = hasCustomSeries ? this.props.labels : defaultLabels;
    const values = (hasCustomSeries ? this.props.values : defaultValues).map(safeNumber);
    new Chart(this.chartRef.el, {
      type: this.props.type,
      data: {
        labels,
        datasets: [
          {
            label: datasetLabel,
            data: values,
            backgroundColor: ["#22c55e", "#fb7185", "#f59e0b", "#38bdf8"].slice(0, labels.length),
            hoverOffset: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: {
              color: "#cbd5f5",
              boxWidth: 10,
              boxHeight: 10,
            },
          },
          title: {
            display: true,
            text: this.props.title,
            position: "bottom",
            color: "#94a3b8",
            font: { size: 12, weight: "500" },
          },
        },
        scales: {
          x: {
            ticks: { color: "#9aa4b2" },
            grid: { color: "rgba(148, 163, 184, 0.15)" },
          },
          y: {
            ticks: { color: "#9aa4b2" },
            grid: { color: "rgba(148, 163, 184, 0.15)" },
          },
        },
      },
    });
  }
}

ChartRenderer.template = "owl.ChartRenderer";
