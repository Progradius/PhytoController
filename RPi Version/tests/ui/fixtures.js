"use strict";

const {test: base} = require("@playwright/test");
const {serveurDeTest} = require("./serveurs");

// Serveur dédié à un scénario.
//
// Le `webServer` de `playwright.config.js` est **unique** et partagé par toute la suite :
// il ne peut porter ni la variable d'environnement d'un scénario (`PHYTO_UI_MEASURE_SCENARIO`)
// ni une mutation qui survivrait aux tests suivants. Un test qui a besoin de l'une ou de
// l'autre démarre donc son propre serveur (`tests/ui/serveurs.js`), comme le carnet, et le
// laisse mourir avec lui.

// Alarme critique de fixture (`_FakeAlarmManager` de `tests/ui_server.py`).
const testAlarmeCritique = base.extend({
  baseURL: [async ({}, use) => {
    test.skip(Boolean(process.env.PHYTO_UI_BASE_URL), "Scénario servi par un serveur local dédié.");
    await serveurDeTest({PHYTO_UI_MEASURE_SCENARIO: "critical"})({}, use);
  }, {scope: "test", timeout: 60000}],
});

// Serveur jetable pour les scénarios qui **écrivent** (créer une coupure) : la coupure ne
// doit pas survivre au test ni fuiter vers les suivants, et jamais viser une cible externe.
const testServeurJetable = base.extend({
  baseURL: [async ({}, use) => {
    test.skip(Boolean(process.env.PHYTO_UI_BASE_URL), "Aucune écriture sur une cible externe.");
    await serveurDeTest({})({}, use);
  }, {scope: "test", timeout: 60000}],
});

// `test.skip` doit exister avant les fixtures ci-dessus : `base` porte les deux.
const test = base;

const historyFixture = () => {
  const end = 1788462000;
  const bucketSeconds = 120;
  const temperatures = [17.2, 18.7, 23.1, 25.4, 23.8, 21.6];
  const humidities = [74, 71, 67, 65, 68, 70];
  const buckets = temperatures.map((temperature, index) => ({
    bucket_start_ts: end - (temperatures.length - index) * bucketSeconds,
    sensors: {
      BME280T: {min: temperature - 0.2, avg: temperature, max: temperature + 0.2, valid_count: 2},
      BME280H: {min: humidities[index] - 1, avg: humidities[index], max: humidities[index] + 1, valid_count: 2},
    },
    sensor_quality: {BME280T: {normal: 2}, BME280H: {normal: 2}},
    setpoints: {temp_min: 18, temp_max: 24, heater_off_threshold: 20, vent_threshold: 24, humidity_threshold: 70},
    actuators: {
      heater: {on_rate: index < 2 ? 1 : 0, min_value: 0, avg_value: index < 2 ? 1 : 0, max_value: 1, valid_count: 2},
      motor: {on_rate: index > 2 ? 1 : 0, min_value: 0, avg_value: index > 2 ? 2 : 0, max_value: index > 2 ? 2 : 0, valid_count: 2},
    },
  }));
  const rangeStart = buckets[0].bucket_start_ts;
  return {
    hours: 24, bucket_seconds: bucketSeconds, max_buckets: 720,
    range_start_ts: rangeStart, range_end_ts: end,
    series: [
      {key: "BME280T", label: "Température air", unit: "°C", decimals: 1, control_role: "climate_temperature"},
      {key: "BME280H", label: "Humidité air", unit: "%", decimals: 1, control_role: "climate_humidity"},
    ],
    equipment: {
      heater: {display_name: "Chauffage"}, motor: {display_name: "Ventilation"},
      daily_1: {display_name: "Éclairage 1"}, daily_2: {display_name: "Éclairage 2"},
      cyclic_1: {display_name: "Sortie cyclique 1"}, cyclic_2: {display_name: "Sortie cyclique 2"},
    },
    buckets,
    events: [{ts: buckets[3].bucket_start_ts, kind: "operator_note", subject: "intervention", payload: {note: "Porte ouverte", alias: "Test"}}],
    actuator_history: {
      heater: {intervals: [{start_ts: rangeStart, end_ts: rangeStart + 240, actual: 1, status: "ok"}, {start_ts: rangeStart + 240, end_ts: end, actual: 0, status: "ok"}], on_seconds: 240, covered_seconds: end - rangeStart, coverage_ratio: 1, transition_count: 1, duration_precision: "exact", speed_seconds: {}},
      motor: {intervals: [{start_ts: rangeStart, end_ts: rangeStart + 360, actual: 0, status: "ok"}, {start_ts: rangeStart + 360, end_ts: end, actual: 2, status: "ok"}], on_seconds: end - rangeStart - 360, covered_seconds: end - rangeStart, coverage_ratio: 1, transition_count: 1, duration_precision: "exact", speed_seconds: {0: 360, 2: end - rangeStart - 360}},
    },
  };
};

module.exports = {historyFixture, testAlarmeCritique, testServeurJetable};
