"""Create a customer and ship-to through native BlueSeer 8.0 transaction APIs."""
import json
import os
from datetime import date
import blue_bridge

CM_FIELDS="""cm_code cm_name cm_line1 cm_line2 cm_line3 cm_city cm_state cm_zip
cm_country cm_dateadd cm_datemod cm_usermod cm_group cm_market cm_creditlimit cm_onhold
cm_carrier cm_terms cm_freight_type cm_price_code cm_disc_code cm_tax_code cm_salesperson
cm_ar_acct cm_ar_cc cm_bank cm_curr cm_remarks cm_label cm_ps_jasper cm_iv_jasper
cm_phone cm_email cm_is855export cm_is856export cm_is810export cm_site cm_misc1
cm_cascade cm_highbal cm_avgdays cm_lastpaydate cm_lastselldate cm_municipality
cm_county cm_tax_exempt""".split()
CMS_FIELDS="""cms_code cms_shipto cms_name cms_line1 cms_line2 cms_line3 cms_city cms_state
cms_zip cms_country cms_contact cms_phone cms_email cms_misc cms_plantcode cms_type
cms_municipality cms_county""".split()

def customer_payload(ticket,code):
    acct=os.getenv("ABD_BLUESEER_AR_ACCOUNT","").strip()
    terms=os.getenv("ABD_BLUESEER_TERMS","").strip()
    if not acct or not terms:
        raise blue_bridge.BridgeError("Set ABD_BLUESEER_AR_ACCOUNT and ABD_BLUESEER_TERMS for customer creation")
    company=blue_bridge.require_config()
    name=ticket["customer"].strip()
    if not name:raise blue_bridge.BridgeError("Customer name is required")
    city=ticket["location"].strip()[:100]
    now=date.today().isoformat()
    cm=blue_bridge.record(CM_FIELDS,cm_code=code,cm_name=name[:120],
        cm_city=city,cm_state="MI",cm_country="US",cm_phone=ticket["phone"][:50],
        cm_county="Manistee",cm_site=os.environ["ABD_BLUESEER_SITE"],
        cm_ar_acct=acct,cm_ar_cc=os.getenv("ABD_BLUESEER_AR_CC",""),
        cm_terms=terms,cm_curr="USD",cm_onhold="0",cm_creditlimit="0",
        cm_dateadd=now,cm_datemod=now,cm_usermod=os.environ["ABD_BLUESEER_USER"])
    cms=blue_bridge.record(CMS_FIELDS,cms_code=code,cms_shipto=code,
        cms_name=name[:120],cms_city=city,cms_state="MI",
        cms_country="US",cms_phone=ticket["phone"][:50],cms_county="Manistee")
    return json.dumps(cm)+"=_=[]=_="+json.dumps(cms)

def upsert_customer(ticket,client=None):
    blue_bridge.require_config()
    client=client or blue_bridge.BlueSeerClient()
    code=(ticket["blue_customer"] if "blue_customer" in ticket.keys() and ticket["blue_customer"] else f"ABD{int(ticket['id']):06d}")
    prior=client.get("dataServCUS","getCustMstr",code)
    if isinstance(prior,dict) and prior.get("cm_code")==code:
        if prior.get("cm_name") and prior["cm_name"].strip().lower()!=ticket["customer"].strip().lower():
            raise blue_bridge.BridgeError("BlueSeer customer ID belongs to a different name; resolve manually")
        return code,"exists"
    payload=customer_payload(ticket,code)
    client.post("dataServCUS","addCustomerTransaction",payload)
    return code,"created"
