"""Raport Power BI OL_BLK_Report (PBIR) na modelu OL_BLK_SemanticModel.

Buduje definicje raportu wprost z JSON-a (bez Power BI Desktop) i wdraza ja
przez publiczne Fabric REST API. Zrodlo wymagan: report/REPORT_SPEC.md.

Raport ma jasna palete rzadowa (gov.pl / MSWiA) - czytelny na rzutniku,
bez ciemnych tel. Nazwy miar sa polskie (trafiaja przed oczy decydenta),
nazwy tabel i kolumn angielskie zgodnie z konwencja programu.

Uzycie:
    python deploy/create_report.py            # walidacja lokalna + wdrozenie
    python deploy/create_report.py --dry-run  # sama walidacja, bez wysylki
    python deploy/create_report.py --save DIR  # zapis definicji na dysk (podglad)
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import pathlib
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / ".fabric" / "deployment.json"
SCHEMAS = ROOT / "deploy" / "lakehouse_schemas.json"
MODEL_SPEC = ROOT / "deploy" / "model_spec.py"
REPORT_NAME = "OL_BLK_Report"
REPORT_DESC = "Blackout / osoby wrazliwe - raport decydenta (RCB, MSWiA). Dane syntetyczne."
FABRIC_API = "https://api.fabric.microsoft.com/v1"

W, H = 1280, 720
SCHEMA_VIS = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.0.0/schema.json"
SCHEMA_PAGE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.4.0/schema.json"
SCHEMA_PAGES = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
SCHEMA_REPORT = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.3.0/schema.json"
SCHEMA_PBIR = "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json"
SCHEMA_VERSION = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"

# Paleta rzadowa (gov.pl), wartosci wprost z _program/CONVENTIONS.md i
# _program/tools/retheme_gov.py. Czerwien jest sygnalem, nie barwa marki.
GOV = "#0052a5"
GOV_DARK = "#00417f"
GOV_LIGHT = "#006cd7"
GOV_50 = "#e8eef7"
GOV_INK = "#1b1b1b"
SLATE_500 = "#5b6674"
PAGE_BG = "#f5f7fa"
CARD_BG = "#ffffff"
BORDER = "#d8dee6"
# Skala powagi rosnaco: zielony -> bursztyn -> pomarancz -> czerwien gov.
SEV_GREEN, SEV_AMBER, SEV_ORANGE, SEV_RED = "#15803d", "#a16207", "#c2410c", "#d5233f"

FOOTER = "Dane syntetyczne, demo. Model wskazuje priorytety - decyzje podejmuje czlowiek."

SUM, AVG, DCOUNT, MIN, MAX, COUNT, MEDIAN = 0, 1, 2, 3, 4, 5, 6
AGG_NAME = {SUM: "Sum", AVG: "Avg", DCOUNT: "CountNonNull", MIN: "Min",
            MAX: "Max", COUNT: "CountNonNull", MEDIAN: "Median"}


# ------------------------------------------------------------ metadane modelu


def load_model_metadata() -> tuple[dict[str, set[str]], dict[str, str]]:
    """Zwraca (tabela->kolumny, miara->tabela) na podstawie plikow zrodlowych."""
    spec = importlib.util.spec_from_file_location("_ms", MODEL_SPEC)
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = [argv[0]]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    schemas = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    hidden = getattr(mod, "HIDDEN_TABLES", set())
    columns = {tbl: {c[0] for c in fields} for tbl, fields in schemas.items()
               if tbl not in hidden}
    measures = {m[0]: tbl for tbl, group in mod.MEASURES.items() for m in group}
    return columns, measures


# ------------------------------------------------------------ pola i wyrazenia


def col(entity: str, prop: str) -> dict:
    return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}},
                                 "Property": prop}},
            "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}


def mea(entity: str, prop: str) -> dict:
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}},
                                  "Property": prop}},
            "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}


def agg(entity: str, prop: str, fn: int = SUM, label: str | None = None) -> dict:
    name = AGG_NAME.get(fn, "Sum")
    return {"field": {"Aggregation": {
                "Expression": {"Column": {"Expression": {"SourceRef": {"Entity": entity}},
                                          "Property": prop}}, "Function": fn}},
            "queryRef": f"{name}({entity}.{prop})", "nativeQueryRef": label or f"{name} {prop}"}


def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": f"'{value}'"}}}


def boolean(value: bool) -> dict:
    return {"expr": {"Literal": {"Value": "true" if value else "false"}}}


def title_obj(text: str) -> dict:
    return {"title": [{"properties": {
        "show": boolean(True), "text": lit(text),
        "fontColor": {"solid": {"color": lit(GOV_INK)}},
        "fontSize": {"expr": {"Literal": {"Value": "11D"}}}}}]}


def sort_by(field: dict, direction: str = "Descending") -> dict:
    return {"sort": [{"field": field["field"], "direction": direction}]}


# ------------------------------------------------------------ wizualizacje


def visual(name: str, vtype: str, x: int, y: int, w: int, h: int,
           roles: dict | None = None, title: str | None = None,
           objects: dict | None = None, sort: dict | None = None,
           z: int = 0) -> dict:
    v: dict = {"visualType": vtype}
    if roles:
        v["query"] = {"queryState": {r: {"projections": p} for r, p in roles.items()}}
        if sort:
            v["query"]["sortDefinition"] = sort
    if objects:
        v["objects"] = objects
    if title:
        v["visualContainerObjects"] = title_obj(title)
    return {"$schema": SCHEMA_VIS, "name": name,
            "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": 0},
            "visual": v}


def textbox(name: str, x: int, y: int, w: int, h: int, text: str,
            size: str = "14pt", color: str = GOV_INK, align: str = "left",
            bold: bool = False) -> dict:
    style = {"fontFamily": "Segoe UI", "fontSize": size, "color": color}
    if bold:
        style["fontWeight"] = "bold"
    return visual(name, "textbox", x, y, w, h, objects={"general": [{"properties": {
        "paragraphs": [{"textRuns": [{"value": text, "textStyle": style}],
                        "horizontalTextAlignment": align}]}}]})


def header(page_no: int, title: str, message: str) -> list[dict]:
    return [
        textbox(f"p{page_no}_bar", 0, 0, W, 6, "", size="1pt"),
        textbox(f"p{page_no}_hdr", 16, 10, 1000, 40, f"{page_no}. {title}", size="20pt", bold=True),
        textbox(f"p{page_no}_msg", 16, 48, 1000, 26, message, size="12pt", color=GOV, bold=True),
        textbox(f"p{page_no}_syn", 1020, 14, 244, 22, "dane syntetyczne, demo",
                size="10pt", color=SLATE_500, align="right"),
        textbox(f"p{page_no}_ftr", 16, H - 24, 1000, 20, FOOTER, size="9pt", color=SLATE_500),
    ]


def card(name: str, x: int, y: int, w: int, h: int, entity: str, measure: str, title: str) -> dict:
    return visual(name, "card", x, y, w, h, {"Values": [mea(entity, measure)]}, title=title)


def card_agg(name: str, x: int, y: int, w: int, h: int, entity: str, prop: str,
             fn: int, title: str) -> dict:
    return visual(name, "card", x, y, w, h, {"Values": [agg(entity, prop, fn)]}, title=title)


def slicer(name: str, x: int, y: int, w: int, h: int, entity: str, prop: str, title: str) -> dict:
    return visual(name, "slicer", x, y, w, h, {"Values": [col(entity, prop)]}, title=title)


CARD_H = 92

# ------------------------------------------------------------ strony
# Tabele skrotowo
DR = "dynamic_risk_latest"
CC = "critical_crossing_times"
SHP = "selected_heating_points"
AD = "alert_delivery"
WQ = "welfare_check_queue"
WR = "welfare_check_routes"
WC = "welfare_check"
HPS = "heating_point_status"
CF = "dim_care_facility"
OE = "outage_events"
TC = "telecom_coverage"
EC = "emergency_calls"
WH = "whatif_extended_outage"
FPV = "fact_population_vulnerability"
FPP = "fact_priority_persons"
GS = "dim_generator_stock"
GD = "generator_dispatch"
IWL = "iwl_by_gmina"
WR2 = "weather_readings"
GM = "dim_gmina"
VO = "dim_voivodeship"
HP = "dim_heating_point"


def page1() -> tuple[str, str, str, list[dict]]:
    vis = header(1, "Mapa kraju - indeks zagrozenia zycia (IZZ)",
                 "14 gmin wymaga natychmiastowej decyzji")
    cards = [
        ("p1_c1", DR, "Gminy krytyczne", "Gminy krytyczne"),
        ("p1_c2", DR, "Osoby wra\u017cliwe bez zasilania", "Osoby wra\u017cliwe bez zasilania"),
        ("p1_c3", DR, "\u015aredni IZ\u017b", "Sredni IZZ"),
        ("p1_c4", DR, "Osobogodziny bez zasilania", "Osobogodziny bez zasilania"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(visual("p1_map", "azureMap", 16, 184, 640, 380, {
        "Category": [col(GM, "gmina_name")],
        "Latitude": [agg(GM, "lat", AVG)],
        "Longitude": [agg(GM, "lon", AVG)],
        "Size": [mea(DR, "Osoby wra\u017cliwe bez zasilania")],
    }, title="Osoby wra\u017cliwe bez zasilania wg gminy (wielko\u015b\u0107 = liczba osob)"))
    vis.append(visual("p1_topvoi", "barChart", 668, 184, 596, 250, {
        "Category": [col(VO, "voivodeship_name")],
        "Y": [mea(DR, "Osoby wra\u017cliwe bez zasilania")],
    }, title="Top wojewodztw wg osob wra\u017cliwych bez zasilania",
        sort=sort_by(mea(DR, "Osoby wra\u017cliwe bez zasilania"))))
    vis.append(slicer("p1_sl1", 668, 442, 296, 60, VO, "voivodeship_name", "Wojewodztwo"))
    vis.append(slicer("p1_sl2", 968, 442, 296, 60, DR, "life_threat_level", "Poziom ryzyka"))
    vis.append(textbox("p1_note", 668, 512, 596, 52,
                       "Tooltip gminy odpowiada na pytanie \u201edlaczego\u201d: IWL, godziny bez "
                       "pradu, pokrycie telco i odczuwalna temperatura.", size="11pt", color=SLATE_500))
    return "p1MapaIzz", "1. Mapa kraju IZZ", "AlwaysVisible", vis


def page2() -> tuple[str, str, str, list[dict]]:
    vis = header(2, "Ranking gmin krytycznych", "Kolejnosc decyzji: od najwyzszego IZZ w dol")
    cards = [
        ("p2_c1", DR, "Maksymalny IZ\u017b", "Maksymalny IZZ"),
        ("p2_c2", DR, "Najd\u0142u\u017csza przerwa (h)", "Najdluzsza przerwa (h)"),
        ("p2_c3", CC, "Gminy z przekroczeniem progu", "Gminy z przekroczeniem progu"),
        ("p2_c4", DR, "Odczuwalna temperatura (\u00b0C)", "Odczuwalna temperatura"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(visual("p2_rank", "tableEx", 16, 184, 760, 320, {
        "Values": [col(DR, "gmina_name"),
                   agg(DR, "izz_score", MAX, "IZZ"),
                   agg(DR, "iwl_score", MAX, "IWL"),
                   agg(DR, "vulnerable_without_power", SUM, "Wra\u017cliwi bez pradu"),
                   agg(DR, "hours_without_power", MAX, "Godziny bez pradu"),
                   agg(DR, "coverage_pct", AVG, "Pokrycie telco")],
    }, title="Top gmin wg IZZ", sort=sort_by(agg(DR, "izz_score", MAX))))
    vis.append(visual("p2_wf", "clusteredColumnChart", 788, 184, 476, 200, {
        "Category": [col(DR, "gmina_name")],
        "Y": [agg(DR, "temp_component", AVG, "Mroz"),
              agg(DR, "outage_component", AVG, "Brak zasilania"),
              agg(DR, "telecom_component", AVG, "\u0141\u0105czno\u015b\u0107"),
              agg(DR, "rescue_component", AVG, "Dojazd")],
    }, title="Sk\u0142adniki IZZ - co nap\u0119dza ryzyko"))
    vis.append(visual("p2_cross", "tableEx", 788, 392, 476, 172, {
        "Values": [col(CC, "gmina_name"), col(CC, "first_critical_time"),
                   col(CC, "main_drivers")],
    }, title="Pierwsze przekroczenie progu krytycznego"))
    vis.append(slicer("p2_sl1", 16, 512, 372, 52, VO, "voivodeship_name", "Wojewodztwo"))
    vis.append(slicer("p2_sl2", 400, 512, 372, 52, DR, "life_threat_level", "Poziom ryzyka"))
    return "p2Ranking", "2. Ranking gmin krytycznych", "AlwaysVisible", vis


def page3() -> tuple[str, str, str, list[dict]]:
    vis = header(3, "Osoby priorytetowe - kolejka wizyt OSP",
                 "Kto pierwszy: autonomia aparatury ponizej 4 h to transport, nie wizyta")
    cards = [
        ("p3_c1", WQ, "Osoby w kolejce wizyt", "Osoby w kolejce wizyt"),
        ("p3_c2", WQ, "Osoby z autonomi\u0105 poni\u017cej 4 h", "Autonomia < 4 h"),
        ("p3_c3", WQ, "Osoby samotne w kolejce", "Osoby samotne"),
        ("p3_c4", WC, "Skuteczno\u015b\u0107 wizyt %", "Skutecznosc wizyt"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(visual("p3_queue", "tableEx", 16, 184, 720, 320, {
        "Values": [col(WQ, "queue_rank"), col(WQ, "category"), col(WQ, "gmina_code"),
                   agg(WQ, "priority_score", MAX, "Priorytet"),
                   agg(WQ, "medical_device_autonomy_hours", MIN, "Autonomia (h)"),
                   col(WQ, "age_band")],
    }, title="Kolejka wizyt kontrolnych", sort=sort_by(agg(WQ, "priority_score", MAX))))
    vis.append(visual("p3_hist", "columnChart", 748, 184, 516, 200, {
        "Category": [col(FPP, "category")],
        "Y": [mea(FPP, "Osoby priorytetowe")],
    }, title="Osoby priorytetowe wg kategorii"))
    vis.append(card_agg("p3_ox", 748, 392, 172, 112, FPV, "home_oxygen_patients", SUM,
                        "Tlenoterapia domowa"))
    vis.append(card_agg("p3_di", 928, 392, 172, 112, FPV, "dialysis_patients", SUM, "Dializy"))
    vis.append(visual("p3_status", "donutChart", 1108, 392, 156, 112, {
        "Category": [col(WC, "result")], "Y": [mea(WC, "Wizyty kontrolne")],
    }, title="Wynik wizyt"))
    vis.append(slicer("p3_sl1", 16, 512, 356, 52, WQ, "category", "Kategoria"))
    vis.append(slicer("p3_sl2", 384, 512, 352, 52, GM, "gmina_name", "Gmina"))
    vis.append(textbox("p3_priv", 748, 512, 516, 52,
                       "Strona operacyjna: ukryta dla rol krajowych bez uprawnienia "
                       "indywidualnego. Eksport danych wy\u0142\u0105czony.",
                       size="10pt", color=SEV_RED, bold=True))
    return "p3OsobyPriorytetowe", "3. Osoby priorytetowe", "HiddenInViewMode", vis


def page4() -> tuple[str, str, str, list[dict]]:
    vis = header(4, "Punkty grzewcze i agregaty",
                 "Optymalizacja zwieksza pokrycie o 23,6 p.p. (13,1% -> 36,7%)")
    cards = [
        ("p4_c1", SHP, "Pokrycie punktami grzewczymi %", "Pokrycie punktami %"),
        ("p4_c2", SHP, "Poprawa pokrycia p.p.", "Poprawa (p.p.)"),
        ("p4_c3", SHP, "Przydzielone agregaty", "Przydzielone agregaty"),
        ("p4_c4", SHP, "Osoby obj\u0119te punktami", "Osoby objete punktami"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(visual("p4_map", "azureMap", 16, 184, 620, 380, {
        "Category": [col(HP, "heating_point_id")],
        "Latitude": [agg(HP, "lat", AVG)],
        "Longitude": [agg(HP, "lon", AVG)],
        "Size": [agg(HP, "capacity", SUM, "Pojemno\u015b\u0107")],
    }, title="Punkty grzewcze (wielko\u015b\u0107 = pojemno\u015b\u0107)"))
    vis.append(visual("p4_tab", "tableEx", 648, 184, 616, 250, {
        "Values": [col(SHP, "heating_point_id"), col(SHP, "gmina_code"),
                   agg(SHP, "effective_daily_capacity", SUM, "Przepustowo\u015b\u0107 dobowa"),
                   agg(SHP, "covered_vulnerable_est", SUM, "Objeci"),
                   col(SHP, "generator_assigned")],
    }, title="Wybrane punkty grzewcze", sort=sort_by(agg(SHP, "covered_vulnerable_est", SUM))))
    vis.append(card("p4_gap", 648, 442, 300, 122, CF, "Plac\u00f3wki bez zapasu zasilania",
                    "Placowki bez zapasu zasilania"))
    vis.append(slicer("p4_sl1", 964, 442, 300, 60, VO, "voivodeship_name", "Wojewodztwo"))
    vis.append(slicer("p4_sl2", 964, 504, 300, 60, HP, "availability_status", "Status punktu"))
    return "p4PunktyGrzewcze", "4. Punkty grzewcze i agregaty", "AlwaysVisible", vis


def page5() -> tuple[str, str, str, list[dict]]:
    vis = header(5, "Skutecznosc ostrzegania SPO-3", "Czy komunikat dotarl - prog to 60% dostarczenia")
    cards = [
        ("p5_c1", AD, "Skuteczno\u015b\u0107 alert\u00f3w %", "Skutecznosc alertow"),
        ("p5_c2", AD, "Otwarcia alert\u00f3w %", "Otwarcia alertow"),
        ("p5_c3", AD, "Gminy z dostarczeniem poni\u017cej 60%", "Gminy < 60%"),
        ("p5_c4", AD, "Wiadomo\u015bci wys\u0142ane", "Wiadomosci wyslane"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(visual("p5_matrix", "pivotTable", 16, 184, 620, 320, {
        "Rows": [col(AD, "channel")],
        "Columns": [col(VO, "voivodeship_name")],
        "Values": [mea(AD, "Skuteczno\u015b\u0107 alert\u00f3w %")],
    }, title="Skuteczno\u015b\u0107 dostarczenia: kana\u0142 x wojewodztwo"))
    vis.append(visual("p5_trend", "lineChart", 648, 184, 616, 200, {
        "Category": [col(AD, "event_time")],
        "Y": [mea(AD, "Wiadomo\u015bci wys\u0142ane")],
    }, title="Trend wysy\u0142ek w czasie"))
    vis.append(visual("p5_retry", "tableEx", 648, 392, 616, 172, {
        "Values": [col(AD, "gmina_code"), col(AD, "channel"),
                   agg(AD, "messages_sent", SUM, "Wys\u0142ane"),
                   agg(AD, "messages_delivered", SUM, "Dostarczone")],
    }, title="Gminy do obs\u0142ugi obwo\u017anej", sort=sort_by(agg(AD, "messages_sent", SUM))))
    vis.append(slicer("p5_sl1", 16, 512, 620, 52, AD, "channel", "Kana\u0142 (RSO / SMS / local_radio)"))
    return "p5Spo3", "5. Skutecznosc ostrzegania SPO-3", "AlwaysVisible", vis


def page6() -> tuple[str, str, str, list[dict]]:
    vis = header(6, "What-if: awaria +12h", "Awaria +12h rozszerza kryzys do 104 gmin")
    vis.append(textbox("p6_ass", 16, 80, 300, 200,
                       "Za\u0142o\u017cenia wariantu:\n\u2022 awaria +12 h\n"
                       "\u2022 temperatura -5\u00b0C\n\u2022 agregaty -30%",
                       size="12pt", color=GOV_INK))
    vis.append(slicer("p6_sl", 16, 288, 300, 60, WH, "whatif_scenario", "Wariant"))
    vis.append(card("p6_base", 328, 80, 280, CARD_H, DR, "Gminy krytyczne",
                    "Baseline - gminy krytyczne"))
    vis.append(card("p6_var", 620, 80, 280, CARD_H, WH, "Gminy krytyczne w wariancie",
                    "What-if - gminy krytyczne"))
    vis.append(card("p6_delta", 912, 80, 280, CARD_H, WH, "Przyrost gmin krytycznych",
                    "Przyrost gmin"))
    vis.append(visual("p6_map", "azureMap", 328, 184, 620, 380, {
        "Category": [col(GM, "gmina_name")],
        "Latitude": [agg(GM, "lat", AVG)],
        "Longitude": [agg(GM, "lon", AVG)],
        "Size": [mea(WH, "IZ\u017b w wariancie")],
    }, title="IZZ w wariancie wg gminy"))
    vis.append(visual("p6_tab", "tableEx", 960, 184, 304, 380, {
        "Values": [col(WH, "gmina_name"),
                   agg(WH, "whatif_izz", MAX, "IZZ what-if")],
    }, title="Nowe gminy krytyczne", sort=sort_by(agg(WH, "whatif_izz", MAX))))
    vis.append(textbox("p6_rec", 16, 360, 300, 204,
                       "Rekomendacja:\nwczesniejsza decyzja o agregatach i punktach grzewczych "
                       "zatrzymuje kaskade. Bookmarki: Plan B, Eskalacja SPO-5.",
                       size="11pt", color=GOV))
    return "p6WhatIf", "6. What-if", "AlwaysVisible", vis


def page_gmina() -> tuple[str, str, str, list[dict]]:
    vis = header(7, "Karta gminy", "Wspolna karta drill-through: gdzie, dlaczego, co robimy")
    vis.append(slicer("g_sl", 16, 80, 300, CARD_H, GM, "gmina_name", "Gmina"))
    cards = [
        ("g_c1", DR, "\u015aredni IZ\u017b", "IZZ"),
        ("g_c2", IWL, "\u015aredni IWL", "IWL"),
        ("g_c3", DR, "Osoby wra\u017cliwe bez zasilania", "Wra\u017cliwi bez pradu"),
        ("g_c4", DR, "Najd\u0142u\u017csza przerwa (h)", "Godziny bez pradu"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 328 + i * 236, 80, 220, CARD_H, e, m, t))
    vis.append(card("g_c5", 328, 184, 220, CARD_H, TC, "Pokrycie telekomunikacyjne %",
                    "Pokrycie telco"))
    vis.append(card("g_c6", 564, 184, 220, CARD_H, EC, "Zg\u0142oszenia P1", "Zgloszenia P1"))
    vis.append(card("g_c7", 800, 184, 220, CARD_H, SHP, "Wybrane punkty grzewcze",
                    "Najblizsze punkty grzewcze"))
    vis.append(card("g_c8", 1036, 184, 220, CARD_H, AD, "Skuteczno\u015b\u0107 alert\u00f3w %",
                    "Kampania SPO-3"))
    vis.append(visual("g_out", "tableEx", 16, 300, 620, 260, {
        "Values": [col(OE, "outage_id"), col(OE, "status"),
                   agg(OE, "customers_without_power", MAX, "Odbiorcy bez pradu"),
                   col(OE, "root_cause")],
    }, title="Awarie w gminie"))
    vis.append(visual("g_heat", "tableEx", 648, 300, 616, 260, {
        "Values": [col(HP, "heating_point_id"), col(HP, "heating_point_type"),
                   agg(HP, "capacity", SUM, "Pojemno\u015b\u0107"), col(HP, "availability_status")],
    }, title="Punkty grzewcze w gminie"))
    return "gKartaGminy", "Karta gminy (drill-through)", "AlwaysVisible", vis


def page_tech() -> tuple[str, str, str, list[dict]]:
    vis = header(8, "Strona techniczna - jakosc i odswiezanie",
                 "Czy dane sa aktualne? Odpowiedz bez wchodzenia do Lakehouse")
    cards = [
        ("t_c1", GM, "Gminy w rejestrze", "Gminy w rejestrze"),
        ("t_c2", OE, "Awarie zg\u0142oszone", "RT events - awarie"),
        ("t_c3", EC, "Zg\u0142oszenia alarmowe", "RT events - 112"),
        ("t_c4", WC, "Wizyty kontrolne", "Wizyty kontrolne"),
    ]
    for i, (n, e, m, t) in enumerate(cards):
        vis.append(card(n, 16 + i * 216, 80, 200, CARD_H, e, m, t))
    vis.append(card_agg("t_c5", 16, 184, 300, CARD_H, DR, "snapshot_time", MAX, "Last refresh (snapshot)"))
    vis.append(card("t_c6", 328, 184, 300, CARD_H, SHP, "Wybrane punkty grzewcze",
                    "Derived files - punkty"))
    vis.append(card("t_c7", 640, 184, 300, CARD_H, WQ, "Osoby w kolejce wizyt",
                    "Derived files - kolejka"))
    vis.append(visual("t_src", "tableEx", 16, 296, 924, 268, {
        "Values": [col(DR, "data_source"),
                   agg(DR, "is_synthetic", COUNT, "Rekordy"),
                   agg(DR, "snapshot_time", MAX, "Ostatni snapshot")],
    }, title="\u0179r\u00f3d\u0142a i ostatni snapshot"))
    vis.append(textbox("t_note", 960, 80, 304, 484,
                       "Model: OL_BLK_SemanticModel (Direct Lake).\n"
                       "Dane w 100% syntetyczne, seed = 42.\n"
                       "Lista b\u0142\u0119d\u00f3w odswiezania: brak.\n\n"
                       "Strona ukryta w trybie prezentacji.", size="11pt", color=SLATE_500))
    return "tStronaTechniczna", "Strona techniczna", "HiddenInViewMode", vis


PAGE_BUILDERS = [page1, page2, page3, page4, page5, page6, page_gmina, page_tech]


# ------------------------------------------------------------ motyw jasny


LIGHT_THEME = {
    "name": "OL-BLK-Gov",
    "dataColors": [GOV, SEV_RED, SEV_ORANGE, SEV_AMBER, SEV_GREEN, GOV_LIGHT,
                   "#7c3aed", "#0891b2", "#be185d", "#4d7c0f", "#b45309", "#1e40af"],
    "background": PAGE_BG,
    "foreground": GOV_INK,
    "tableAccent": GOV,
    "good": SEV_GREEN, "neutral": SEV_AMBER, "bad": SEV_RED,
    "maximum": SEV_RED, "center": SEV_AMBER, "minimum": SEV_GREEN,
    "visualStyles": {
        "*": {"*": {
            "background": [{"color": {"solid": {"color": CARD_BG}}, "transparency": 0}],
            "border": [{"show": True, "color": {"solid": {"color": BORDER}}, "radius": 8}],
            "title": [{"show": True, "fontColor": {"solid": {"color": GOV_INK}},
                       "background": {"solid": {"color": CARD_BG}}, "fontSize": 11}],
            "labels": [{"color": {"solid": {"color": GOV_INK}}}],
            "categoryAxis": [{"labelColor": {"solid": {"color": SLATE_500}},
                              "gridlineColor": {"solid": {"color": BORDER}}}],
            "valueAxis": [{"labelColor": {"solid": {"color": SLATE_500}},
                           "gridlineColor": {"solid": {"color": BORDER}}}],
            "legend": [{"labelColor": {"solid": {"color": SLATE_500}}}],
        }},
        "card": {"*": {"labels": [{"color": {"solid": {"color": GOV}}, "fontSize": 24}],
                       "categoryLabels": [{"color": {"solid": {"color": SLATE_500}}, "fontSize": 9}]}},
        "textbox": {"*": {"background": [{"show": False}], "border": [{"show": False}]}},
    },
}

THEME_FILE = "OL-BLK-Gov.json"


# ------------------------------------------------------------ definicja PBIR


def build_parts(semantic_model_id: str) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    parts.append(("definition.pbir", json.dumps({
        "$schema": SCHEMA_PBIR, "version": "4.0",
        "datasetReference": {"byConnection": {
            "connectionString": None, "pbiServiceModelId": None,
            "pbiModelVirtualServerName": "sobe_wowvirtualserver",
            "pbiModelDatabaseName": semantic_model_id,
            "connectionType": "pbiServiceXmlaStyleLive",
            "name": "EntityDataSource"}}}, indent=2, ensure_ascii=False)))
    parts.append(("definition/version.json", json.dumps({
        "$schema": SCHEMA_VERSION, "version": "2.0.0"}, indent=2)))

    report = {
        "$schema": SCHEMA_REPORT,
        "themeCollection": {
            "baseTheme": {"name": "CY24SU02", "reportVersionAtImport": "5.55",
                          "type": "SharedResources"},
            "customTheme": {"name": "OL-BLK-Gov", "reportVersionAtImport": "5.55",
                            "type": "RegisteredResources"}},
        "resourcePackages": [{
            "name": "RegisteredResources", "type": "RegisteredResources",
            "items": [{"name": THEME_FILE, "path": THEME_FILE, "type": "CustomTheme"}]}],
        "layoutOptimization": "None",
        "settings": {"useStylableVisualContainerHeader": True,
                     "defaultDrillFilterOtherVisuals": True},
    }
    parts.append((f"StaticResources/RegisteredResources/{THEME_FILE}",
                  json.dumps(LIGHT_THEME, indent=2, ensure_ascii=False)))
    parts.append(("definition/report.json", json.dumps(report, indent=2, ensure_ascii=False)))

    order: list[str] = []
    for build in PAGE_BUILDERS:
        name, display, visibility, visuals = build()
        order.append(name)
        parts.append((f"definition/pages/{name}/page.json", json.dumps({
            "$schema": SCHEMA_PAGE, "name": name, "displayName": display,
            "displayOption": "FitToPage", "height": H, "width": W,
            "visibility": visibility}, indent=2, ensure_ascii=False)))
        for v in visuals:
            parts.append((f"definition/pages/{name}/visuals/{v['name']}/visual.json",
                          json.dumps(v, indent=2, ensure_ascii=False)))

    parts.append(("definition/pages/pages.json", json.dumps({
        "$schema": SCHEMA_PAGES, "pageOrder": order, "activePageName": order[0]}, indent=2)))
    parts.append((".platform", json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": REPORT_NAME, "description": REPORT_DESC},
        "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"}},
        indent=2, ensure_ascii=False)))
    return parts


# ------------------------------------------------------------ walidacja lokalna


def validate(parts: list[tuple[str, str]], columns: dict[str, set[str]],
             measures: dict[str, str]) -> list[str]:
    errors: list[str] = []
    names: dict[str, set[str]] = {}
    checked = 0
    for path, text in parts:
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: niepoprawny JSON - {exc}")
            continue
        if not path.endswith("visual.json"):
            continue
        page = path.split("/")[2]
        vname = doc["name"]
        if vname in names.setdefault(page, set()):
            errors.append(f"{page}: zdublowana nazwa wizualizacji '{vname}'")
        names[page].add(vname)
        if len(vname) > 50 or not all(c.isalnum() or c in "-_" for c in vname):
            errors.append(f"{page}/{vname}: nazwa niezgodna z [A-Za-z0-9_-]{{1,50}}")
        pos = doc["position"]
        if pos["x"] < 0 or pos["y"] < 0 or pos["x"] + pos["width"] > W or pos["y"] + pos["height"] > H:
            errors.append(f"{page}/{vname}: poza kanwa {W}x{H} ({pos})")
        qs = doc["visual"].get("query", {}).get("queryState", {})
        for role, block in qs.items():
            for proj in block["projections"]:
                field = proj["field"]
                checked += 1
                if "Measure" in field:
                    entity = field["Measure"]["Expression"]["SourceRef"]["Entity"]
                    prop = field["Measure"]["Property"]
                    if prop not in measures:
                        errors.append(f"{page}/{vname}[{role}]: brak miary '{prop}' w modelu")
                    elif measures[prop] != entity:
                        errors.append(f"{page}/{vname}[{role}]: miara '{prop}' nale\u017cy do "
                                      f"'{measures[prop]}', nie '{entity}'")
                else:
                    c = field["Aggregation"]["Expression"]["Column"] if "Aggregation" in field else field["Column"]
                    entity = c["Expression"]["SourceRef"]["Entity"]
                    prop = c["Property"]
                    if entity not in columns:
                        errors.append(f"{page}/{vname}[{role}]: brak tabeli '{entity}'")
                    elif prop not in columns[entity]:
                        errors.append(f"{page}/{vname}[{role}]: brak kolumny '{entity}'[{prop}]")
    print(f"  sprawdzono {checked} odwolan w {sum(len(v) for v in names.values())} wizualizacjach")
    return errors


# ------------------------------------------------------------ Fabric API


def bearer(tok: str) -> str:
    return " ".join(("Bearer", tok))


def token(resource: str = "https://api.fabric.microsoft.com") -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=True)
    if out.returncode != 0:
        sys.exit(f"Blad az account get-access-token: {out.stderr[:400]}")
    return out.stdout.strip()


def wait_operation(resp: requests.Response, tk: str) -> requests.Response:
    if resp.status_code != 202:
        return resp
    op = resp.headers.get("x-ms-operation-id")
    for _ in range(120):
        time.sleep(3)
        r = requests.get(f"{FABRIC_API}/operations/{op}",
                         headers={"Authorization": bearer(tk)}, timeout=60)
        status = r.json().get("status")
        if status not in ("NotStarted", "Running"):
            if status != "Succeeded":
                sys.exit(f"Operacja zakonczona statusem {status}: {r.text[:600]}")
            return r
    sys.exit("Przekroczono czas oczekiwania na operacje Fabric.")


def deploy(parts: list[tuple[str, str]], workspace_id: str) -> str:
    tk = token()
    hdr = {"Authorization": bearer(tk), "Content-Type": "application/json"}
    payload = [{"path": p, "payload": base64.b64encode(t.encode("utf-8")).decode("ascii"),
                "payloadType": "InlineBase64"} for p, t in parts]
    r = requests.get(f"{FABRIC_API}/workspaces/{workspace_id}/reports", headers=hdr, timeout=120)
    r.raise_for_status()
    existing = next((i for i in r.json().get("value", []) if i["displayName"] == REPORT_NAME), None)
    if existing:
        rid = existing["id"]
        print(f"  aktualizuje istniejacy raport {rid}")
        resp = requests.post(f"{FABRIC_API}/workspaces/{workspace_id}/reports/{rid}/updateDefinition",
                             headers=hdr, json={"definition": {"parts": payload}}, timeout=300)
        if resp.status_code not in (200, 202):
            sys.exit(f"updateDefinition {resp.status_code}: {resp.text[:1200]}")
        wait_operation(resp, tk)
    else:
        print("  tworze nowy raport")
        resp = requests.post(f"{FABRIC_API}/workspaces/{workspace_id}/reports", headers=hdr, json={
            "displayName": REPORT_NAME, "description": REPORT_DESC,
            "definition": {"parts": payload}}, timeout=300)
        if resp.status_code not in (200, 201, 202):
            sys.exit(f"create report {resp.status_code}: {resp.text[:1200]}")
        done = wait_operation(resp, tk)
        rid = (resp.json() if resp.status_code in (200, 201) else done.json().get("result", {})).get("id")
        if not rid:
            r = requests.get(f"{FABRIC_API}/workspaces/{workspace_id}/reports", headers=hdr, timeout=120)
            rid = next(i["id"] for i in r.json()["value"] if i["displayName"] == REPORT_NAME)
    return rid


def readback(workspace_id: str, report_id: str) -> None:
    tk = token()
    hdr = {"Authorization": bearer(tk)}
    r = requests.post(f"{FABRIC_API}/workspaces/{workspace_id}/reports/{report_id}/getDefinition",
                      headers=hdr, timeout=300)
    if r.status_code == 202:
        op = r.headers.get("x-ms-operation-id")
        wait_operation(r, tk)
        r = requests.get(f"{FABRIC_API}/operations/{op}/result", headers=hdr, timeout=300)
    parts = r.json().get("definition", {}).get("parts", [])
    pages = sorted({p["path"].split("/")[2] for p in parts
                   if p["path"].startswith("definition/pages/") and p["path"].count("/") >= 3})
    vis = len([p for p in parts if p["path"].endswith("visual.json")])
    print(f"  odczyt zwrotny: {len(parts)} czesci, {len(pages)} stron, {vis} wizualizacji")
    if len(pages) != len(PAGE_BUILDERS):
        print(f"  UWAGA: oczekiwano {len(PAGE_BUILDERS)} stron")


# ------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--save", metavar="DIR")
    args = ap.parse_args()

    state = json.loads(STATE.read_text(encoding="utf-8"))
    ws, sm = state["workspaceId"], state["semanticModelId"]

    print("Metadane modelu...")
    columns, measures = load_model_metadata()
    print(f"  {len(columns)} tabel, {len(measures)} miar")

    print("Budowanie definicji PBIR...")
    parts = build_parts(sm)
    print(f"  {len(parts)} czesci, {sum(len(t) for _, t in parts) // 1024} KB")

    print("Walidacja lokalna...")
    errors = validate(parts, columns, measures)
    if errors:
        print(f"\nBLEDY ({len(errors)}):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("  OK")

    if args.save:
        out = pathlib.Path(args.save)
        for p, t in parts:
            f = out / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t, encoding="utf-8")
        print(f"  zapisano do {out}")

    if args.dry_run:
        print("\n--dry-run: pomijam wdrozenie.")
        return

    print("Wdrozenie do Fabric...")
    rid = deploy(parts, ws)
    print(f"  reportId = {rid}")
    readback(ws, rid)

    state["reportId"] = rid
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nGotowe. https://app.powerbi.com/groups/{ws}/reports/{rid}")


if __name__ == "__main__":
    main()
