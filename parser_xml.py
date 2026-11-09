import xml.etree.ElementTree as ET
from typing import Dict, Any

# Namespaces estándar del SAT para CFDI v3.3 y v4.0
NAMESPACES = {
    'cfdi': 'http://www.sat.gob.mx/cfd/4',
    'cfdi33': 'http://www.sat.gob.mx/cfd/3',
    'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'
}

def parsear_factura_xml(file_bytes: bytes) -> Dict[str, Any]:
    """
    Parsea el contenido binario de un archivo XML de factura mexicana (CFDI).
    Extrae datos clave: Fecha, Tipo (I/E), RFC Emisor, Subtotal, Tasa IVA, Monto IVA, Total y Estatus.
    """
    try:
        root = ET.fromstring(file_bytes)
    except ET.ParseError:
        raise ValueError("El archivo subido no es un XML válido.")

    # 1. Determinar versión del CFDI y namespace correspondiente
    version = root.attrib.get('Version', root.attrib.get('version', '4.0'))
    ns = {'cfdi': NAMESPACES['cfdi33']} if version == '3.3' else {'cfdi': NAMESPACES['cfdi']}

    # 2. Atributos generales del comprobante (Insensible a mayúsculas/minúsculas)
    fecha_raw = root.attrib.get('Fecha') or root.attrib.get('fecha') or ''
    fecha = fecha_raw.split('T')[0] if 'T' in fecha_raw else fecha_raw

    subtotal_str = root.attrib.get('SubTotal') or root.attrib.get('Subtotal') or root.attrib.get('subtotal') or '0.0'
    total_str = root.attrib.get('Total') or root.attrib.get('total') or '0.0'

    try:
        subtotal = float(subtotal_str)
    except ValueError:
        subtotal = 0.0

    try:
        total = float(total_str)
    except ValueError:
        total = 0.0

    # Tipo de Comprobante: I = Ingreso (Trasladado), E = Egreso/Gasto (Acreditable)
    tipo_comprobante = root.attrib.get('TipoDeComprobante') or root.attrib.get('tipoDeComprobante') or 'I'
    tipo_comprobante = tipo_comprobante.upper()

    # Estatus dinámico (Procesado, Pendiente, Rechazado)
    estatus = root.attrib.get('Estatus') or root.attrib.get('estatus') or 'Procesado'

    # 3. Datos del Emisor y Receptor
    emisor_node = root.find('cfdi:Emisor', ns)
    rfc_emisor = emisor_node.attrib.get('Rfc') or emisor_node.attrib.get('rfc') or 'DESCONOCIDO' if emisor_node is not None else 'DESCONOCIDO'
    nombre_emisor = emisor_node.attrib.get('Nombre') or emisor_node.attrib.get('nombre') or '' if emisor_node is not None else ''

    receptor_node = root.find('cfdi:Receptor', ns)
    rfc_receptor = receptor_node.attrib.get('Rfc') or receptor_node.attrib.get('rfc') or '' if receptor_node is not None else ''

    # 4. Extraer Impuestos (Desglose de IVA)
    monto_iva = 0.0
    tasa_iva_str = "16%"

    impuestos_node = root.find('cfdi:Impuestos', ns)
    if impuestos_node is not None:
        traslados_node = impuestos_node.find('cfdi:Traslados', ns)
        if traslados_node is not None:
            for traslado in traslados_node.findall('cfdi:Traslado', ns):
                impuesto = traslado.attrib.get('Impuesto') or traslado.attrib.get('impuesto') or ''
                # '002' es el código oficial del SAT para IVA
                if impuesto == '002':
                    monto_str = traslado.attrib.get('Importe') or traslado.attrib.get('importe') or '0.0'
                    tasa_str = traslado.attrib.get('TasaOCuota') or traslado.attrib.get('tasaOCuota') or '0.16'
                    
                    try:
                        monto_iva += float(monto_str)
                        tasa_ocuota = float(tasa_str)
                        tasa_iva_str = f"{int(round(tasa_ocuota * 100))}%"
                    except ValueError:
                        pass

    # Si no se encontró el nodo de Impuestos consolidado, buscar a nivel Conceptos
    if monto_iva == 0.0:
        conceptos_node = root.find('cfdi:Conceptos', ns)
        if conceptos_node is not None:
            for concepto in conceptos_node.findall('cfdi:Concepto', ns):
                imp_concepto = concepto.find('cfdi:Impuestos', ns)
                if imp_concepto is not None:
                    tras_concepto = imp_concepto.find('cfdi:Traslados', ns)
                    if tras_concepto is not None:
                        for tras in tras_concepto.findall('cfdi:Traslado', ns):
                            imp_code = tras.attrib.get('Impuesto') or tras.attrib.get('impuesto')
                            if imp_code == '002':
                                m_str = tras.attrib.get('Importe') or tras.attrib.get('importe') or '0.0'
                                try:
                                    monto_iva += float(m_str)
                                except ValueError:
                                    pass

    return {
        "fecha": fecha,
        "rfc_emisor": rfc_emisor,
        "nombre_emisor": nombre_emisor,
        "rfc_receptor": rfc_receptor,
        "subtotal": round(subtotal, 2),
        "tasa_iva": tasa_iva_str,
        "monto_iva": round(monto_iva, 2),
        "total": round(total, 2),
        "tipo_comprobante": tipo_comprobante,
        "estatus": estatus
    }