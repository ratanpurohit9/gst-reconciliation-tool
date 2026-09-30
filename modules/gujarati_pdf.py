"""Gujarati vendor notices rendered with Pango/HarfBuzz through WeasyPrint.

Gujarati is complex-script text. This renderer keeps it as Unicode and lets the
Pango text stack perform shaping before WeasyPrint embeds the selected font.
"""
from datetime import date
from html import escape

from weasyprint import HTML


def _text(value):
    return escape("" if value is None else str(value))


def _money(value):
    try:
        if value is None:
            return "—"
        number = float(value)
        if number != number:
            return "—"
        return f"₹{number:,.2f}"
    except (TypeError, ValueError):
        return "—"


def _rows_for_status(df, status):
    subset = df[df["Recon_Status"] == status]
    rows = []
    for _, row in subset.iterrows():
        books_inv = row.get("Invoice Number_BOOKS", "")
        portal_inv = row.get("Invoice Number_GST", "")
        books_inv = "" if books_inv is None else str(books_inv)
        portal_inv = "" if portal_inv is None else str(portal_inv)
        if books_inv.lower() == "nan":
            books_inv = ""
        if portal_inv.lower() == "nan":
            portal_inv = ""
        inv = portal_inv or books_inv or "—"
        date_value = row.get("Invoice Date_GST")
        if date_value is None or str(date_value) == "NaT":
            date_value = row.get("Invoice Date_BOOKS")
        try:
            date_value = date_value.strftime("%d-%m-%Y")
        except (AttributeError, ValueError):
            date_value = str(date_value or "—")
        rows.append({
            "invoice": inv,
            "date": date_value,
            "taxable": row.get("Taxable Value_BOOKS", 0) or 0,
            "igst": row.get("IGST_BOOKS", 0) or 0,
            "cgst": row.get("CGST_BOOKS", 0) or 0,
            "sgst": row.get("SGST_BOOKS", 0) or 0,
            "total": sum(float(row.get(key, 0) or 0) for key in (
                "Taxable Value_BOOKS", "IGST_BOOKS", "CGST_BOOKS", "SGST_BOOKS"
            )),
        })
    return rows


def create_vendor_pdf_gujarati(df, vendor_name, company_name, gst_in_company,
                               vendor_gstin, translations, status_config):
    issue_mask = df["Recon_Status"].astype(str).str.contains(
        "Not in|Mismatch|Suggestion|Manual|Tax Error", na=False
    )
    vendor_df = df[(df["Name of Party"] == vendor_name) & issue_mask].copy()
    if vendor_df.empty:
        return b""

    statuses = list(dict.fromkeys(vendor_df["Recon_Status"].astype(str).tolist()))
    count = len(vendor_df)
    taxable_total = sum(sum(row["taxable"] for row in _rows_for_status(vendor_df, st))
                        for st in statuses)
    gst_total = sum(sum(row["igst"] + row["cgst"] + row["sgst"]
                        for row in _rows_for_status(vendor_df, st))
                    for st in statuses)
    t = translations["gu"]

    sections = []
    for status in statuses:
        cfg = status_config(status, "gu")
        rows = _rows_for_status(vendor_df, status)
        table_rows = "".join(
            "<tr><td>{}</td><td>{}</td><td class='num'>{}</td>"
            "<td class='num'>{}</td><td class='num'>{}</td><td class='num'>{}</td>"
            "<td class='num strong'>{}</td></tr>".format(
                i, _text(row["invoice"]), _text(row["date"]),
                _money(row["taxable"]), _money(row["igst"]),
                _money(row["cgst"]), _money(row["sgst"]), _money(row["total"])
            )
            for i, row in enumerate(rows, 1)
        )
        # Keep approved Gujarati action/note only for the sample status.
        actions = cfg["action"] if isinstance(cfg["action"], (list, tuple)) else [cfg["action"]]
        action_html = "".join(f"<li>{_text(action)}</li>" for action in actions)
        note = ""
        if status == "Invoices Not in GSTR-2B":
            note = f"<p class='note'>{_text(t['delay'])}</p>"
        sections.append(f"""
          <section class="issue">
            <div class="issue-title"><strong>{_text(cfg['label'])}</strong>
              <span>{len(rows)} Invoice(s)</span></div>
            <p class="description">{_text(cfg['desc'])}</p>
            <table class="invoices">
              <thead><tr><th>Sr.</th><th>Invoice No.</th><th>Invoice Date</th>
              <th>Taxable Value</th><th>IGST</th><th>CGST</th><th>SGST</th>
              <th>Total Invoice Value</th></tr></thead>
              <tbody>{table_rows}</tbody>
              <tfoot><tr><td colspan="3">TOTAL ({len(rows)} Inv.)</td>
                <td>{_money(sum(r['taxable'] for r in rows))}</td>
                <td>{_money(sum(r['igst'] for r in rows))}</td>
                <td>{_money(sum(r['cgst'] for r in rows))}</td>
                <td>{_money(sum(r['sgst'] for r in rows))}</td>
                <td>{_money(sum(r['total'] for r in rows))}</td></tr></tfoot>
            </table>
            <div class="actions"><strong>{_text(t['action'])}</strong>
              <ol>{action_html}</ol>{note}</div>
          </section>""")

    html = f"""<!doctype html><html lang="gu"><head><meta charset="utf-8">
    <style>
      @page {{ size:A4; margin:15mm 15mm 17mm;
        @bottom-center {{ content:"{_text(company_name)} | GSTIN: {_text(gst_in_company)} | Page " counter(page) " | Generated: {date.today().strftime('%d-%m-%Y')}";
          color:#888; font:7pt Arial,sans-serif; }} }}
      * {{ box-sizing:border-box; }}
      body {{ color:#1a1a2e; font:9pt "Noto Sans Gujarati",sans-serif; line-height:1.5; }}
      .latin {{ font-family:Arial,sans-serif; }}
      .header {{ display:flex; justify-content:space-between; align-items:center;
        background:#1f3864; color:white; padding:10px 14px; margin-bottom:10px; }}
      .brand {{ font:bold 14pt Arial,sans-serif; }}
      .brand small {{ display:block; font:7pt Arial,sans-serif; color:#d6e4f0; }}
      .title {{ font-size:12pt; font-weight:bold; text-align:right; }}
      .title small {{ display:block; font:7pt Arial,sans-serif; }}
      .to {{ border:1px solid #2e75b6; border-left:4px solid #2e75b6;
        background:#ebf3fb; padding:8px 12px; margin:8px 0; }}
      .to .name {{ font:bold 11pt Arial,sans-serif; color:#1f3864; margin:3px 0; }}
      .to .gst {{ font:8pt Arial,sans-serif; color:#555; }}
      .subject {{ font-weight:bold; margin:10px 0 5px; }}
      .intro {{ margin:6px 0 10px; }}
      .summary {{ display:flex; border:1px solid #2e75b6; background:#f5f8fc; margin:8px 0 12px; }}
      .metric {{ flex:1; padding:8px; border-right:1px solid #ccd7e3; }}
      .metric:last-child {{ border:0; }}
      .metric label {{ display:block; color:#555; font-size:8pt; }}
      .metric b {{ font:bold 12pt Arial,sans-serif; color:#1f3864; }}
      .issue {{ margin:12px 0; break-inside:avoid; }}
      .issue-title {{ display:flex; justify-content:space-between; align-items:center;
        background:#c00000; color:white; padding:7px 9px; }}
      .issue-title span {{ font:8pt Arial,sans-serif; }}
      .description {{ margin:6px 4px; }}
      table.invoices {{ width:100%; border-collapse:collapse; font:7pt Arial,sans-serif; }}
      .invoices th {{ background:#1f3864; color:white; }}
      .invoices th,.invoices td {{ border:1px solid #aab6c4; padding:4px 3px; }}
      .invoices tfoot {{ background:#d6e4f0; font-weight:bold; }}
      .num {{ text-align:right; white-space:nowrap; }}
      .strong {{ font-weight:bold; color:#1f3864; }}
      .actions {{ margin-top:6px; padding:7px 10px; background:#fff2f2;
        border:1px solid #c00000; border-left:4px solid #c00000; }}
      .actions strong {{ color:#c00000; }}
      .actions ol {{ margin:5px 0; padding-left:22px; }}
      .note {{ border-top:1px solid #e6b4b4; margin:5px -4px -2px; padding:6px 4px 0; font-size:8pt; }}
      .closing {{ border-top:1px solid #ccc; margin-top:12px; padding-top:8px; }}
      .signature {{ margin-top:18px; font:9pt Arial,sans-serif; }}
      .signature .line {{ width:135px; border-top:1px solid #999; margin-top:26px; }}
    </style></head><body>
      <header class="header">
        <div class="brand">{_text(company_name)}<small>GSTIN: {_text(gst_in_company)}</small></div>
        <div class="title">{_text(t['title'])}<small>{_text(t['date'])}: {date.today().strftime('%d-%m-%Y')}</small></div>
      </header>
      <div class="to">{_text(t['to'])}<br/><span class="latin">The Accounts / GST Department</span>
        <div class="name">{_text(vendor_name)}</div><div class="gst">GSTIN: {_text(vendor_gstin)}</div></div>
      <div class="subject">{_text(t.get('subject_tag','વિષય:'))} {_text(t['subject'])}</div>
      <p class="intro">{t['intro'].format(n=count, k=len(statuses))}</p>
      <div class="summary">
        <div class="metric"><label>{_text(t['summary'][0])}</label><b>{count}</b></div>
        <div class="metric"><label>{_text(t['summary'][1])}</label><b>{_money(taxable_total)}</b></div>
        <div class="metric"><label>{_text(t['summary'][2])}</label><b>{_money(gst_total)}</b></div>
      </div>
      {''.join(sections)}
      <p class="closing">{_text(t['close'])}</p>
      <div class="signature"><div>{_text(t['faith'])}</div><div class="line"></div>
        <strong>{_text(t['sign'])}<br/>{_text(company_name)}</strong><br/>
        GSTIN: {_text(gst_in_company)}</div>
    </body></html>"""
    # WeasyPrint uses Pango/HarfBuzz for complex-script shaping and embeds fonts.
    pdf = HTML(string=html, base_url=".").write_pdf()
    return pdf

