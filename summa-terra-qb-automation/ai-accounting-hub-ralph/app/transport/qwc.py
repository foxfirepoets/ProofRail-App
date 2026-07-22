"""Generate the QBWC ``.qwc`` registration file and a minimal WSDL.

The Web Connector imports a ``.qwc`` to learn the endpoint URL + identity; it then
fetches the WSDL at that URL to bind the SOAP methods. Both are static here.
"""
from __future__ import annotations

import uuid
from xml.sax.saxutils import escape

_DEFAULT_OWNER_ID = "{57F3B9B5-86F1-4FCC-B1EE-566DE1813D20}"


def build_qwc(
    app_name: str,
    app_url: str,
    username: str,
    *,
    app_description: str = "AI Accounting Hub read-only sync",
    file_id: str | None = None,
    owner_id: str = _DEFAULT_OWNER_ID,
    run_every_min: int = 5,
) -> str:
    """Return a ``.qwc`` document registering this endpoint with the Web Connector."""
    file_id = file_id or "{" + str(uuid.uuid4()).upper() + "}"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<QBWCXML>\n"
        f"  <AppName>{escape(app_name)}</AppName>\n"
        f"  <AppID></AppID>\n"
        f"  <AppURL>{escape(app_url)}</AppURL>\n"
        f"  <AppDescription>{escape(app_description)}</AppDescription>\n"
        f"  <AppSupport>{escape(app_url)}</AppSupport>\n"
        f"  <UserName>{escape(username)}</UserName>\n"
        f"  <OwnerID>{owner_id}</OwnerID>\n"
        f"  <FileID>{file_id}</FileID>\n"
        "  <QBType>QBFS</QBType>\n"
        f"  <Scheduler><RunEveryNMinutes>{run_every_min}</RunEveryNMinutes></Scheduler>\n"
        "  <IsReadOnly>true</IsReadOnly>\n"
        "</QBWCXML>\n"
    )


# Minimal QBWC WSDL. The Web Connector only needs the five method bindings; full
# message/type detail mirrors Intuit's published QBWebConnectorSvc contract.
WSDL = """<?xml version="1.0" encoding="utf-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:tns="http://developer.intuit.com/"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    targetNamespace="http://developer.intuit.com/" name="QBWebConnectorSvc">
  <wsdl:service name="QBWebConnectorSvc">
    <wsdl:documentation>QBWC outbound-poll endpoint: authenticate, sendRequestXML,
    receiveResponseXML, getLastError, closeConnection.</wsdl:documentation>
  </wsdl:service>
</wsdl:definitions>
"""
