/** @odoo-module */

const { Component } = owl;

export class KpiCard extends Component {}
KpiCard.props = ["done", "label", "variant"];
KpiCard.template = "owl.KpiCard";
