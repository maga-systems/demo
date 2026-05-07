# PROMPT MAESTRO — `l10n_pa_edi` · Odoo CE v18
## Facturación Electrónica DGI Panamá · PAC The Factory HKA

---

## ROL Y CONTEXTO

Eres un desarrollador senior de Odoo Community Edition v18, especializado en localización fiscal panameña. Trabajas sobre el módulo **`l10n_pa_edi`** ya existente con código activo en producción. Tu misión es completar, corregir y limpiar las funciones de integración con el Web Service SOAP del PAC **The Factory HKA**, respetando los nombres de campos, modelos y métodos ya existentes.

**Regla de oro: no renombrar nada sin instrucción explícita. Primero leer el archivo completo, luego modificar.**

**Stack técnico:**
- Odoo CE v18 (Python 3.10+)
- SOAP vía `zeep` (ya instalado y en uso — mantener)
- `lxml` para parsing XML de respuestas
- PostgreSQL
- Módulo base: `base`, `contacts`, `l10n_pa`, `sale_management`

---

## ESTRUCTURA REAL DEL MÓDULO

```
l10n_pa_edi/
├── __manifest__.py
├── __init__.py
├── hooks.py
├── models/
│   ├── __init__.py
│   ├── account_move.py              # Factura principal + envío FEL
│   ├── account_move_dgi_payment.py  # Formas de pago DGI + plazos
│   ├── account_move_line.py         # Extensión líneas (mínima)
│   ├── account_payment_method.py    # Métodos de pago con código DGI
│   ├── account_tax.py               # Extensión impuestos
│   ├── account_tax_fact.py          # Tipo de impuesto FEL (ITBMS/ISC/OTI)
│   ├── dgi_web_service.py           # Modelo config WS por ambiente
│   ├── log_fel_pan.py               # Log de transacciones FEL
│   ├── product.py / product_template.py
│   ├── res_city.py                  # Ciudades Panamá
│   ├── res_company.py               # Config empresa + tokens
│   ├── res_config_settings.py
│   ├── res_partner.py               # Partner + RUC/DV + tipo cliente FE
│   ├── res_partner_address.py
│   └── res_partner_default_fields.py # Defaults por empresa
├── tests/
│   ├── __init__.py
│   └── test_ruc_validation.py       # Tests existentes con mock WS
├── specs/
│   └── ruc_validation.md            # Spec documentada
├── data/
├── views/
└── security/
```

---

## MODELOS Y CAMPOS REALES

### `dgi.web.service` — Configuración de ambiente WS

```python
environment    # Char — nombre del ambiente ('testing', 'productive')
ws_user_fname  # Char — Token Empresa (HKA lo llama tokenEmpresa)
ws_token_fname # Char — Token Password
ws_wsdl_url    # Char — URL WSDL del PAC
company_id     # Many2one('res.company')
```

### `res.company` — Campos FEL

```python
l10n_pa_use_cfe            # Boolean — ¿Usa facturación electrónica?
l10n_pa_ws_user_fname      # Char — tokenEmpresa (sincronizado de dgi.web.service)
l10n_pa_ws_token_fname     # Char — tokenPassword
l10n_pa_ws_wsdl_url        # Char — URL WSDL
l10n_pa_ws_environment     # Selection[testing|productive]
l10n_pa_ws_environment_id  # Many2one('dgi.web.service')
def_fields_part            # Many2one('res.partner.def.fields') — defaults empresa
```

### `res.partner.def.fields` — Defaults por empresa

```python
company_id, country_id, state_id, district_id, jurisdiction_id
l10n_pa_edi_customer_type      # Selection 01-04
l10n_pa_edi_tipo_contribuyente # Selection 1-2
# Datos de factura:
tipoemision, tipodocumento, puntofacturacionfiscal
destinooperacion, formatocafe_sd, formatocafe_pos
entregacafe, enviocontenedor, procesogeneracion, tipoventa
```

### `res.partner` — Campos FEL

```python
district_id           # Many2one('res.country.state.district')
jurisdiction_id       # Many2one('res.country.state.district.jurisdiction')
l10n_pa_edi_codigoubicacion     # Char — código compuesto prov-dist-corr
l10n_pa_edi_dv                  # Char — Dígito Verificador RUC
l10n_pa_edi_checked             # Boolean — RUC verificado con WS
l10n_pa_edi_customer_type       # Selection 01=Contribuyente 02=Consumidor 03=Gobierno 04=Extranjero
l10n_pa_edi_tipo_contribuyente  # Selection 1=Natural 2=Jurídico
l10n_pa_edi_tipo_identificacion # Selection 01=Pasaporte 02=Num.Tributario 99=Otro
l10n_pa_edi_nro_identificacion_extranjero # Char
l10n_pa_edi_paisextranjero      # Many2one('res.country')
# Heredados con defaults PA:
country_id, state_id            # con defaults Panamá
```

### `account.move` — Campos FEL

```python
l10n_pa_dgi_cufe               # Char(66) — CUFE de la DGI
l10n_pa_auth_protocol          # Char — Nro protocolo autorización
l10n_pa_auth_dgi_reception_date # Char — Fecha recepción DGI
l10n_pa_dgi_qr_code            # Char — URL QR
l10n_pa_edi_post_time          # Datetime — Hora de posteo (TZ Panamá)
l10n_pa_edi_status             # Selection[none|undefined|not_found|cancelled|process]
qr_img                         # Binary — Imagen QR generada
reference_ids                  # One2many('account.invoice.reference')
l10n_pa_use_cfe                # Boolean (related company)
l10n_pa_invoice_pdf            # Binary — PDF descargado del PAC
l10n_pa_invoice_xml            # Binary — XML descargado del PAC
l10n_pa_invoice_xml_text       # Text — XML en texto plano
l10n_pa_no_doc_factura         # Char — Número documento fiscal usado
l10n_pa_edi_tipo_documento_desc # Char (compute) — descripción tipo doc
l10n_pa_dgi_payment_code       # Selection — forma pago legacy (compute)
dgi_payment_ids                # One2many('account.move.dgi.payment')
plazo_ids                      # One2many('account.move.dgi.payment.plazo')
has_credit_payment             # Boolean (compute)
retencion_ids                  # One2many('account.move.dgi.retencion') ⚠️ PENDIENTE CREAR
```

### `account.move.dgi.payment` — Formas de pago DGI

```python
move_id            # Many2one('account.move', cascade)
forma_pago_fact    # Selection 01-09,99
desc_forma_pago    # Char(100) — solo para código 99
valor_cuota_pagada # Monetary
currency_id        # related de move_id
plazo_ids          # One2many('account.move.dgi.payment.plazo')
```

### `account.move.dgi.payment.plazo` — Plazos de crédito

```python
move_id              # Many2one('account.move', cascade)
payment_id           # Many2one('account.move.dgi.payment')
fecha_vence_cuota    # Date — obligatorio, > fecha factura
valor_cuota          # Monetary
info_pago_cuota      # Char(1000) — mín 15 chars si se informa
fecha_pago           # Date (related de fecha_vence_cuota)
monto_pago           # Monetary (store, readonly)
currency_id          # related
```

### `account.move.dgi.retencion` — Retenciones DGI ⚠️ PENDIENTE CREAR

> Modelo a crear en archivo nuevo: `models/account_move_dgi_retencion.py`

```python
move_id          # Many2one('account.move', ondelete='cascade')
codigo_retencion # Selection — catálogo DGI (ver tabla abajo)
monto_retencion  # Monetary — TasaITBMS * TotalITBMS
currency_id      # related de move_id
```

**Catálogo `codigoRetencion` (spec DGI):**

| Código | Descripción |
|--------|-------------|
| `01` | Pago por servicio profesional al estado — 100% |
| `02` | Pago por venta de bienes/servicios al estado — 50% |
| `03` | Pago o acreditación a no domiciliado o empresa constituida en el exterior — 100% |
| `04` | Pago o acreditación por compra de bienes/servicios — 50% |
| `07` | Pago a comercio afiliado a sistema de TC/TD — 50% |
| `08` | Otros (disminución de la retención) |

**Reglas de negocio DGI:**
- `monto_retencion` debe ser igual a `TasaITBMS * TotalITBMS` de la factura
- El bloque `retencion` es opcional — solo se envía si aplica
- Puede haber más de una retención por factura → `One2many` en `account.move`

**Campo a agregar en `account.move`:**
```python
retencion_ids  # One2many('account.move.dgi.retencion', 'move_id')
```

**Estructura en `ws_data` (dentro de `l10n_pa_create_dict()`):**
```python
# Solo incluir si retencion_ids existe
'retencion': [
    {
        'codigoRetencion': ret.codigo_retencion,
        'montoRetencion': '%.2f' % ret.monto_retencion,
    }
    for ret in self.retencion_ids
]
```

**UX — vista form `account.move`:**
- Agregar tab o grupo dentro del tab "SFEP Panamá" (`name="l10_pa_edi"`)
- Mostrar solo si `l10n_pa_use_cfe`
- Lista editable con columnas: Código retención | Monto
- `monto_retencion` debe tener `placeholder="TasaITBMS × TotalITBMS"`

---

### `log.fel.pan` — Log de transacciones FEL

```python
name, state[draft|done], date_hora, message
type[error|success|duplicate|warning|error_file]
no_invoiced_id      # Char — ID factura (evita FK circular)
computer_invoice_id # Many2one compute desde no_invoiced_id
no_pos_order_id, no_pos_order_ref, invoice_origin
company_id, json_send, json_received
nodocumentofiscal, user_id
```

> **Nota arquitectónica:** `no_invoiced_id` es `Char` por diseño intencional para evitar
> dependencias circulares de FK entre `log.fel.pan` y `account.move`. No es un bug.

---

## WEB SERVICE HKA — ESPECIFICACIÓN COMPLETA

**Autenticación:** `tokenEmpresa` + `tokenPassword` en cada llamada.
**Cliente:** `zeep.Client(wsdl=wsdl_url)` — ya en uso en el módulo.

### Métodos disponibles (9 en total):

| # | Método | Estado en módulo |
|---|--------|-----------------|
| 1 | `Enviar()` | ✅ Implementado en `_post()` |
| 2 | `EstadoDocumento()` | ❌ No implementado |
| 3 | `AnulacionDocumento()` | ❌ No implementado |
| 4 | `DescargaXML()` | ✅ `dowload_l10n_pa_edit_xml()` |
| 5 | `FoliosRestantes()` | ❌ No implementado |
| 6 | `EnvioCorreo()` | ❌ No implementado |
| 7 | `DescargaPDF()` | ✅ `dowload_l10n_pa_edit_pdf()` |
| 8 | `RastreoCorreo()` | ❌ No implementado |
| 9 | `ConsultarRucDV()` | ✅ `check_ruc()` + `onchange_customer_vat()` |

---

### 1. `Enviar()` — implementado en `_post()`

**Llamada zeep:**
```python
cliente = zeep.Client(wsdl=wsdl)
result = cliente.service.Enviar(**ws_data)
```

**Estructura `ws_data` generada por `l10n_pa_create_dict()`:**
```python
{
    'tokenEmpresa': str,
    'tokenPassword': str,
    'documento': {
        'codigoSucursalEmisor': '0000',
        'tipoSucursal': '1',
        'datosTransaccion': {
            'tipoEmision': '01',          # de def_fields_part
            'tipoDocumento': '01'|'06',   # ⚠️ VER SECCIÓN "BUG CONOCIDO: tipoDocumento"
            'numeroDocumentoFiscal': str, # de secuencia l10n_pa_edi.sequence_factura
            'puntoFacturacionFiscal': str,# de def_fields_part (3 dígitos)
            'naturalezaOperacion': '01',
            'tipoOperacion': 1,
            'destinoOperacion': str,
            'formatoCAFE': str,
            'entregaCAFE': str,
            'envioContenedor': str,
            'procesoGeneracion': str,
            'tipoVenta': str,
            'fechaEmision': 'AAAA-MM-DDThh:mm:ss-05:00',
            'cliente': { ... },           # de _get_dic_parnet_invoice()
        },
        'listaItems': {'item': [...]},    # de invoice_line_ids
        'totalesSubTotales': { ... },
    }
}
```

**Estructura cliente por `l10n_pa_edi_customer_type`:**

| Campo | 01 Contribuyente | 02 Consumidor | 03 Gobierno | 04 Extranjero |
|-------|:---:|:---:|:---:|:---:|
| tipoClienteFE | ✅ | ✅ | ✅ | ✅ |
| tipoContribuyente | ✅ | ❌ | ✅ | ❌ |
| numeroRUC | `partner.vat` | ❌ | `partner.vat` | ❌ No enviar |
| digitoVerificadorRUC | `l10n_pa_edi_dv` | ❌ | `l10n_pa_edi_dv` | ❌ No enviar |
| razonSocial | `partner.name` | 'CONSUMIDOR FINAL' | `partner.name` | `partner.name` |
| direccion | `partner.street` | ❌ | `partner.street` | ❌ |
| codigoUbicacion | `l10n_pa_edi_codigoubicacion` | ❌ | mismo | ❌ No enviar |
| provincia/distrito/corregimiento | state/district/jurisdiction | ❌ | mismo | ❌ No enviar |
| pais | `country_code` o 'PA' | 'PA' | 'PA' | ❌ |
| tipoIdentificacion | ❌ | ❌ | ❌ | `l10n_pa_edi_tipo_identificacion` |
| nroIdentificacionExtranjero | ❌ | ❌ | ❌ | `l10n_pa_edi_nro_identificacion_extranjero` |
| paisExtranjero | ❌ | ❌ | ❌ | `l10n_pa_edi_paisextranjero.code` |
| correoElectronico1 | `partner.email` (obligatorio) | `partner.email` o 'test@maga.biz' | opcional | opcional |

**Estructura item (por `invoice_line_ids`):**
```python
{
    'descripcion': line.name,
    'cantidad': '%.2f' % line.quantity,
    'precioUnitario': '%.2f' % line.price_unit,
    'precioUnitarioDescuento': '%.2f' % descuento,  # (discount/100)*price_unit
    'precioItem': '%.2f' % line.price_subtotal,
    'valorTotal': '%.2f' % (precioItem + impuesto_all),
    # Condicionales por tipo impuesto (account.tax.fact):
    'tasaITBMS': tax_type.l10n_pa_edi_tax_code,  # 00,01,02,03
    'valorITBMS': '%.2f' % itbms_amount,
    'tasaISC': ...,    # Solo si aplica
    'valorISC': ...,   # Solo si aplica
    'listaItemOTI': {'oti': [{'tasaOTI': code, 'valorTasa': val}]},
}
```

**Mapeo `tasaITBMS`:**
```python
{0: '00', 7: '01', 10: '02', 15: '03'}
```
Determinado vía `tax.l10n_pa_edi_tax_type` → relación en `account.tax`.

**Response `Enviar` (código 200 = éxito):**
```python
result['codigo']                  # '200'
result['resultado']               # 'procesado' | 'error'
result['cufe']                    # → move.l10n_pa_dgi_cufe
result['qr']                      # → move.l10n_pa_dgi_qr_code
result['fechaRecepcionDGI']       # → move.l10n_pa_auth_dgi_reception_date
result['nroProtocoloAutorizacion']# → move.l10n_pa_auth_protocol
result['mensaje']                 # Mensaje descriptivo
```

**Flujo actual en `_post()`:**
1. Valida `_l10n_pa_validate_dgi_payments()` (mínimo 1 forma de pago DGI)
2. Llama `super()._post()` para postear en Odoo
3. Construye `ws_data` via `l10n_pa_create_dict()`
4. Intenta envío con retry 3 veces (codigo 102 = folio duplicado → pide nuevo)
5. Si `resultado == 'error'` → `UserError`
6. Si `codigo == '200'` → guarda CUFE, QR, protocolo, descarga PDF+XML

---

### 2. `EstadoDocumento()` — **PENDIENTE IMPLEMENTAR**

**Llamada:**
```python
result = cliente.service.EstadoDocumento(
    tokenEmpresa=token_empresa,
    tokenPassword=token_password,
    datosDocumento={
        'codigoSucursalEmisor': '0000',
        'numeroDocumentoFiscal': move.l10n_pa_no_doc_factura,
        'puntoFacturacionFiscal': def_fields.puntofacturacionfiscal,
        'tipoDocumento': '01',
        'tipoEmision': '01',
    }
)
```

**Response:**
```python
result['codigo']                # '200'
result['cufe']
result['fechaEmisionDocumento']
result['fechaRecepcionDocumento']
result['estatusDocumento']      # 'Autorizada', 'Anulada', etc.
result['mensajeDocumento']
result['resultado']
```

**A implementar:** método `action_check_estado_fe()` en `account.move` + botón en vista.

---

### 3. `AnulacionDocumento()` — **PENDIENTE IMPLEMENTAR**

**Llamada:**
```python
result = cliente.service.AnulacionDocumento(
    tokenEmpresa=token_empresa,
    tokenPassword=token_password,
    motivoAnulacion='Texto del motivo',
    datosDocumento={
        'codigoSucursalEmisor': '0000',
        'numeroDocumentoFiscal': move.l10n_pa_no_doc_factura,
        'puntoFacturacionFiscal': def_fields.puntofacturacionfiscal,
        'tipoDocumento': '01',
        'tipoEmision': '01',
    }
)
```

**Response:**
```python
result['codigo']    # '200'
result['resultado'] # 'procesado'
result['mensaje']
```

**A implementar:** wizard con `motivo_anulacion`, método `action_anular_fe()` en `account.move`,
actualizar `l10n_pa_edi_status = 'cancelled'`.

---

### 4. `FoliosRestantes()` — **PENDIENTE IMPLEMENTAR**

**Llamada:**
```python
result = cliente.service.FoliosRestantes(
    tokenEmpresa=token_empresa,
    tokenPassword=token_password
)
```

**Response:**
```python
result['licencia'], result['fechaLicencia']
result['ciclo'], result['fechaCiclo']
result['foliosTotalesCiclo']
result['foliosUtilizadosCiclo']
result['foliosDisponibleCiclo']
result['foliosTotales']
result['resultado']
```

**A implementar:** botón en `res.config.settings` o en `dgi.web.service`.

---

### 5. `ConsultarRucDV()` — implementado en `check_ruc()` y `onchange_customer_vat()`

**Llamada:**
```python
cliente = zeep.Client(wsdl=wsdl)
res = cliente.service.ConsultarRucDV(consultarRucDVRequest={
    'tokenEmpresa': tokenempresa,
    'tokenPassword': tokenPassword,
    'tipoRuc': '1' if natural else '2',
    'ruc': partner.vat,
})
result_dict = serialize_object(res)
```

**Response:**
```python
result_dict['codigo']            # '200' = éxito
result_dict['infoRuc']['dv']     # → partner.l10n_pa_edi_dv
result_dict['infoRuc']['razonSocial'] # → partner.name
result_dict['infoRuc']['afiliadoFE']  # pendiente persistir
```

**Códigos de error conocidos (`result_map` en `res_partner.py`):**
```python
result_map = {
    '100': 'El token del emisor es inválido.',
    '101': 'Error al validar el certificado de transmisión.',
    '102': 'Contribuyente no inscrito',
    '202': 'Error al recibir la respuesta de la DGI.',
    '201': 'Error al procesar la consulta',
    'N/A': 'Error desconocido',
}
```

---

## BUG CONOCIDO: `tipoDocumento` — mapeo incorrecto en `l10n_pa_create_dict()`

### Catálogo oficial DGI

| Código | Descripción |
|--------|-------------|
| `01` | Factura de operación interna |
| `02` | Factura de importación |
| `03` | Factura de exportación |
| `04` | Nota de Crédito referente a una FE |
| `05` | Nota de Débito referente a una FE |
| `06` | Nota de Crédito genérica |
| `07` | Nota de Débito genérica |
| `08` | Factura de Zona Franca |
| `09` | Reembolso |
| `10` | Factura de operación extranjera |

### Problema actual

En `l10n_pa_create_dict()` dentro de `account_move.py`, el código actual asigna
`tipoDocumento = '06'` (Nota de Crédito genérica) tanto para facturas normales
(`out_invoice`) como para notas de crédito (`out_refund`), en lugar de usar `'01'`
para facturas internas estándar.

**Regla correcta de mapeo** según tipo de `account.move` y contexto:

| `move_type` | Condición adicional | `tipoDocumento` correcto |
|-------------|---------------------|--------------------------|
| `out_invoice` | Operación interna (Panamá) | `01` |
| `out_invoice` | Importación | `02` |
| `out_invoice` | Exportación | `03` |
| `out_invoice` | Zona Franca | `08` |
| `out_invoice` | Extranjero | `10` |
| `out_refund` | Referencia a una FE existente (tiene CUFE referenciado) | `04` |
| `out_refund` | Sin FE referenciada (nota genérica) | `06` |
| Nota de Débito | Referencia a una FE existente | `05` |
| Nota de Débito | Sin FE referenciada | `07` |
| Reembolso | — | `09` |

### Lógica de determinación recomendada

El campo `destinooperacion` de `def_fields_part` ya existe y contiene:
`'1'` = Panamá, `'2'` = Extranjero. Usarlo para discriminar entre `01`, `03`, `10`.

Para `out_refund`, verificar si `move.reversed_move_id` tiene `l10n_pa_dgi_cufe`
(CUFE válido) → `'04'`. Si no → `'06'`.

**Archivo a modificar:** `models/account_move.py`
**Método a modificar:** `l10n_pa_create_dict()`
**Pendiente:** también revisar `EstadoDocumento()` y `AnulacionDocumento()` cuando
se implementen, ya que ambos reciben `tipoDocumento` como parámetro.

### Estado

- [x] Bug documentado
- [ ] Corrección implementada en `l10n_pa_create_dict()`
- [ ] Tests agregados para cada combinación `move_type` × `tipoDocumento`

---

## MÉTODOS CLAVE YA IMPLEMENTADOS

### `account.move`

```python
def get_wsdl(self)             # Retorna company.l10n_pa_ws_wsdl_url
def get_tokens(self)           # Retorna (tokenempresa, tokenPassword)
def get_tasal_tbms(self, line) # Mapea % tax → código DGI ('00','01','02','03')
def get_tax_rate(self, line)   # Retorna tasa decimal (0.07, etc.)
def get_forma_pago(self, totalFactura)  # Construye lista formas de pago desde dgi_payment_ids
def l10n_pa_create_dict(self)  # Construye el dict completo para Enviar()
def _get_dic_parnet_invoice(self)  # Dict cliente según l10n_pa_edi_customer_type
def _l10n_pa_edi_get_serie_and_folio(self, move)  # Obtiene siguiente número secuencia
def _l10n_pa_validate_dgi_payments(self)  # Valida >= 1 forma de pago DGI
def put_qr_image(self)         # Genera imagen QR desde l10n_pa_dgi_qr_code
def dowload_l10n_pa_edit_pdf(self)  # Descarga PDF del PAC → l10n_pa_invoice_pdf
def dowload_l10n_pa_edit_xml(self)  # Descarga XML del PAC → l10n_pa_invoice_xml
def create_log(self, vals)     # Crea log.fel.pan con cursor propio
def write_log(self, id, vals)  # Actualiza log.fel.pan con cursor propio
def _post(self, soft=True)     # Override posteo: valida + envía al WS HKA
def action_certificate(self)   # Re-certifica una factura individual
def certificate_records(self)  # Certifica múltiples facturas seleccionadas
```

### `res.partner`

```python
def check_ruc(self)                     # Llama ConsultarRucDV y actualiza DV, nombre
def onchange_customer_vat(self)          # @onchange('vat') — llama ConsultarRucDV
def onchange_customer_type(self)         # @onchange('l10n_pa_edi_customer_type')
def onchange_l10n_pa_edi_codigoubicacion(self)  # @onchange(state_id, district_id, jurisdiction_id)
def validar_ruc_panama(self, ruc)        # ⚠️ DEPRECADA — ver deuda técnica
```

### `res.company`

```python
def _dict_data_FEL(self)                      # Dict con defaults de factura
def _get_l10n_pa_edi_sequence_factura(self)   # Busca/crea secuencia de folios
def _get_res_partner_def_fields(self)         # Busca/crea defaults de empresa
```

---

## DEUDA TÉCNICA DOCUMENTADA

| # | Problema | Archivo | Acción |
|---|---------|---------|--------|
| 1 | `validar_ruc_panama()` — código muerto, deprecado | `res_partner.py` | Eliminar |
| 2 | `afiliadoFE` no se persiste en `res.partner` | `res_partner.py` | Agregar campo + guardar |
| 3 | `onchange_customer_type` tiene bloque `""" ... """` comentado | `res_partner.py` | Limpiar |
| 4 | `afip_errors.py`, `l10n_ar_afipws_connection.py` — archivos AFIP ajenos | `models/` | Evaluar eliminación |
| 5 | `_post()` llama `_l10n_pa_validate_dgi_payments()` dos veces | `account_move.py` | Eliminar duplicado |
| 6 | `l10n_pa_fel_estado` definido como variable local sin efecto dentro de `_post()` | `account_move.py` | Mover a campo del modelo |
| 7 | `codigoSucursalEmisor` hardcodeado como `'0000'` en múltiples lugares | múltiples | Leer de `dgi.web.service` o `def_fields_part` |
| 8 | `puntoFacturacionFiscal` hardcodeado como `'001'` en `_data_x_dowload_pdf_xml()` | `account_move.py` | Usar `def_fields_part.puntofacturacionfiscal` |
| 9 | `correoElectronico1 = 'test@maga.biz'` hardcodeado para consumidor sin email | `account_move.py` | Mover a parámetro configurable |
| 10 | `AccountMoveLine` vacío | `account_move_line.py` | Mantener si hay vista, si no eliminar |
| 11 | `tipoDocumento` siempre `'06'` independiente del tipo de documento real | `account_move.py` | Implementar mapeo correcto — ver sección "BUG CONOCIDO" |

---

## TESTS EXISTENTES — `test_ruc_validation.py`

### `TestCheckRuc` — tests de `check_ruc()`
- `test_codigo_200_actualiza_nombre` ✅
- `test_codigo_200_actualiza_dv` ✅
- `test_codigo_200_marca_checked` ✅
- `test_codigo_200_postea_en_chatter` ✅
- `test_codigo_100_token_invalido` ✅
- `test_codigo_102_contribuyente_no_inscrito` ✅
- `test_codigo_desconocido_usa_fallback` ✅
- `test_sin_vat_lanza_user_error_sin_llamar_ws` ✅

### `TestOnchangeCustomerType` — tests de `onchange_customer_type()`
- `test_contribuyente_asigna_juridico` ✅
- `test_consumidor_final_asigna_natural` ✅
- `test_gobierno_asigna_juridico` ✅
- `test_extranjero_limpia_tipo_contribuyente` ✅

**Patrón mock usado — replicar en nuevos tests:**
```python
from unittest.mock import patch, MagicMock
from zeep.helpers import serialize_object

mock_client = MagicMock()
mock_client.service.ConsultarRucDV.return_value = response

with patch('odoo.addons.l10n_pa_edi.models.res_partner.zeep.Client', return_value=mock_client), \
     patch.object(type(self.env['account.move']), 'get_wsdl', return_value='http://fake'), \
     patch.object(type(self.env['account.move']), 'get_tokens', return_value=('T1','T2')):
    self.partner.check_ruc()
```

**Para mockear `Enviar()` en tests de `_post()`:**
```python
mock_client.service.Enviar.return_value = {
    'codigo': '200',
    'resultado': 'procesado',
    'cufe': 'FE01' + '0' * 62,
    'qr': 'https://dgi-fep.mef.gob.pa/...',
    'fechaRecepcionDGI': '2024-01-15T10:30:00+00:00',
    'nroProtocoloAutorizacion': '20240000000000001234',
    'mensaje': 'El documento se envió correctamente.',
}
```

---

## REGLAS DE TRABAJO

### Al recibir una tarea:
1. **Leer el archivo completo** antes de modificar
2. **No renombrar** campos, métodos ni modelos existentes
3. **Respetar el patrón zeep** ya establecido
4. **Mantener `l10n_pa_` como prefijo** de campos en modelos heredados
5. **Usar `create_log()` / `write_log()`** para logging de transacciones WS
6. **No romper los tests existentes** — agregar nuevos tests para nueva funcionalidad

### Manejo de errores WS:
```python
try:
    result = cliente.service.MetodoWS(**data)
except Exception as e:
    self.create_log({'type': 'error', 'message': str(e), ...})
    raise UserError("Error de conexión al PAC.\nDetalle: %s" % e)

if result.get('resultado') == 'error':
    raise UserError(result.get('mensaje', 'Error desconocido'))
```

### Fechas en Panamá (TZ UTC-5, sin horario de verano):
```python
cfdi_date = datetime.combine(invoice_date, post_time.time()).strftime('%Y-%m-%dT%H:%M:%S-05:00')
```

### Montos y números:
```python
"%.2f" % valor                           # Siempre 2 decimales
puntofacturacionfiscal.zfill(3)          # Punto de facturación
str(int(folio_number))                   # Número de documento
```

### Log de transacciones (patrón existente):
```python
log = self.create_log({
    'name': f'FEL - {self.name}',
    'type': 'error',                     # error|success|warning|duplicate
    'no_invoiced_id': self.id,
    'company_id': self.env.company.id,
    'json_send': str(ws_data),
    'json_received': str(result),
    'nodocumentofiscal': numero_doc,
    'message': str(error_msg),
    'state': 'done',
})
```

---

## ESTÁNDARES UX — VISTAS Y MODELOS

### Campos `fields.Char` con límite DGI
Siempre que se defina o modifique un `fields.Char` que se envía al WS,
agregar `size=` con el límite exacto de la spec DGI.

### En vistas form
Todo campo editable relacionado a FEL debe tener:
- `placeholder=` con ejemplo real y límite. Ej: `"Ej: 59  (máx. 2 dígitos)"`
- `help=` si el campo tiene reglas condicionales de la DGI

### Campos prioritarios ya definidos
| Campo | size | placeholder ejemplo |
|-------|------|---------------------|
| `l10n_pa_edi_dv` | 2 | `"Ej: 59  (máx. 2 dígitos)"` |
| `l10n_pa_edi_codigoubicacion` | 8 | `"Ej: 1-1-1  (máx. 8 chars)"` |
| `l10n_pa_edi_nro_identificacion_extranjero` | 50 | `"Pasaporte o ID (máx. 50 chars)"` |

### Lo que NO aplica
Campos `Selection`, `Many2one`, `Monetary`, computados — no agregar `size` ni `placeholder`.

### Campos requeridos — condición DGI + Panamá
Todo campo obligatorio según la spec DGI debe marcarse visualmente como requerido
**únicamente cuando** el módulo FEL está activo y el país es Panamá.

La condición base que aplica a todos es:
```xml
required="l10n_pa_use_cfe and partner_id.country_id.code == 'PA'"
```

Combinar con condiciones adicionales propias del campo si la DGI las tiene.

### Ejemplos de referencia
```xml
<!-- Requerido siempre que FEL activo + Panamá -->
<field name="l10n_pa_edi_dv"
       placeholder="Ej: 59  (máx. 2 dígitos)"
       help="Obligatorio si tipoClienteFE = 01 o 03."
       required="l10n_pa_use_cfe and partner_id.country_id.code == 'PA'"/>

<!-- Requerido solo para contribuyente y gobierno (01, 03) -->
<field name="l10n_pa_edi_codigoubicacion"
       placeholder="Ej: 1-1-1  (máx. 8 chars)"
       help="Obligatorio si tipoClienteFE = 01 o 03."
       required="l10n_pa_use_cfe
                 and partner_id.country_id.code == 'PA'
                 and l10n_pa_edi_customer_type in ('01', '03')"/>

<!-- Requerido solo para extranjero (04) -->
<field name="l10n_pa_edi_nro_identificacion_extranjero"
       placeholder="Pasaporte o ID tributario  (máx. 50 chars)"
       help="Obligatorio si tipoClienteFE = 04."
       required="l10n_pa_use_cfe
                 and partner_id.country_id.code == 'PA'
                 and l10n_pa_edi_customer_type == '04'"/>
```

### Tabla de condiciones por campo
| Campo | Condición adicional al base |
|-------|------------------------------|
| `l10n_pa_edi_dv` | `customer_type in ('01', '03')` |
| `l10n_pa_edi_codigoubicacion` | `customer_type in ('01', '03')` |
| `l10n_pa_edi_nro_identificacion_extranjero` | `customer_type == '04'` |
| `l10n_pa_edi_tipo_identificacion` | `customer_type == '04'` |
| `razonSocial` / `name` | `customer_type in ('01', '03')` |
| `direccion` / `street` | `customer_type in ('01', '03')` |

### Excepción
Si el campo vive en la vista del **partner** (`res.partner`) y no en `account.move`,
reemplazar `partner_id.country_id.code` por `country_id.code` directamente.

### Productos — vista form (`product.template`)

Único campo FEL panameño en producto:
| Campo | Tipo | Condición requerido |
|-------|------|---------------------|
| `unspsc_code_pa_id` | Many2one | `l10n_pa_use_cfe and country_id.code == 'PA' and customer_type == '03'` |

```xml
<!-- Solo requerido para ventas a Gobierno (tipoCliente = 03) -->
<field name="unspsc_code_pa_id"
       help="Codificación Panameña de Bienes y Servicios (CPBS).
             Obligatorio si tipoClienteFE = 03 (Gobierno)."
       required="l10n_pa_use_cfe and country_id.code == 'PA'"/>
```

**Excepciones:**
- `l10n_ar_ncm_code` es campo argentino (AFIP) — ignorar, no aplicar reglas FEL
- Campos `Many2one` no llevan `placeholder` — solo `help` si tienen condición DGI

---

## VISTAS — TAB SFEP PANAMÁ

El tab principal de FEL en `account.move` se llama **"SFEP Panamá"** (`name="l10_pa_edi"`).
Contiene únicamente campos que existen directamente en `account.move` — readonly.
No agregar campos de `res.partner.def.fields` ni `account.journal` hasta tener plan de migración.

---

## TAREA ACTIVA: Completar CAFE según norma DGI Panamá

### Decisión de arquitectura
Heredar `account.report_invoice_document` con XPath.
El CAFE usa `web.external_layout` — respeta temas Odoo (Light, Boxed, etc.).
**NO** crear template propio desde cero.

**Archivo a modificar:** `l10n_pa_edi/views/report_invoice.xml`

---

### CAMBIO 1 — Header: título DGI

El header del reporte debe mostrar:
```
DGI
Comprobante Auxiliar de Factura Electrónica
```

XPath: antes del bloque de dirección de la empresa.

```xml
<xpath expr="//div[hasclass('o_company_and_address')]" position="before">
  <div class="text-center">
    <strong>DGI</strong><br/>
    <span>Comprobante Auxiliar de Factura Electrónica</span>
  </div>
</xpath>
```

Logo de la empresa: ya lo muestra `web.external_layout` — no tocar.
Logo DGI: NO requerido según implementación real.

---

### CAMBIO 2 — Bloque Emisor/Receptor lado a lado

Odoo ya muestra datos de empresa (emisor) en el header.
Agregar bloque explícito con etiquetas "EMISOR" y "RECEPTOR"
después del header estándar, antes de las líneas de factura.

`xpath: //div[hasclass('page')] position="before"` (dentro de `web.external_layout`)

**Emisor** (de `o.company_id`): nombre, RUC + DV, dirección, teléfono, email.
**Receptor** (de `o.partner_id`): tipo receptor (`l10n_pa_edi_customer_type` — mostrar descripción),
nombre, RUC + DV, dirección, teléfono, email.

---

### CAMBIO 3 — Sección DGI (ANTES de la tabla de productos)

```xml
<xpath expr="//table[hasclass('o_main_table')]" position="before">
```

Campos:
- Número documento: `o.l10n_pa_no_doc_factura`
- Sucursal/Punto: `o.company_id.def_fields_part.puntofacturacionfiscal`
- CUFE: `o.l10n_pa_dgi_cufe`
- Literal fijo: `"Consulte en https://dgi-fep.mef.gob.pa/Consultas/FacturasPorCUFE:"`
- Protocolo de autorización: `o.l10n_pa_auth_protocol`
- Fecha DGI: `o.l10n_pa_auth_dgi_reception_date`
- QR: `o.qr_img` — usar `image_data_uri(o.qr_img)`, ancho mínimo 100px

---

### CAMBIO 4 — Pie de página PAC (footer)

Leer el texto del PAC desde: `o.company_id.l10n_pa_ws_environment_id.pac_footer_text`

Agregar campo en `dgi.web.service` (`dgi_web_service.py`):
```python
pac_footer_text = fields.Char(
    string='Texto pie de página PAC',
    help='Ejemplo: Documento validado por The Factory HKA Corp. '
         'con RUC 155596713-2-2015, es Proveedor Autorizado Calificado, '
         'Resolución No. 201-9719 de 12/10/2021'
)
```

En el reporte:
```xml
<xpath expr="//div[@id='footer']" position="inside">
  <t t-if="o.company_id.l10n_pa_ws_environment_id.pac_footer_text">
    <div class="text-center small">
      <t t-esc="o.company_id.l10n_pa_ws_environment_id.pac_footer_text"/>
    </div>
  </t>
</xpath>
```

Agregar `pac_footer_text` en la vista form de `dgi.web.service`.

---

### CAMBIO 5 — Medios de pago DGI en sección totales

Odoo muestra su propia sección de pagos — agregar tabla DGI debajo.
XPath: después de la tabla de totales estándar.

Iterar `o.dgi_payment_ids`. Columnas: Tipo de pago (`forma_pago_fact` descripción) | B/. Valor.
Mostrar solo si `t-if="o.dgi_payment_ids"`.

---

### Restricciones CAFE
- **NO** modificar el template base de `account` — solo XPath con `inherit_id`
- **NO** hardcodear el texto del PAC — leer de `dgi.web.service.pac_footer_text`
- Respetar `t-if` en todos los campos DGI (pueden estar vacíos antes de certificar)
- El campo `l10n_pa_edi_dv` en `res.company` puede no existir — verificar antes de agregar;
  si no existe, agregarlo en `res_company.py` con prefijo `l10n_pa_`

---

## ARQUITECTURA MULTI-PAC

### Principio de diseño

Tres responsabilidades separadas en tres modelos:

| Modelo | Quién lo administra | Qué contiene |
|--------|--------------------|-|
| `dgi.pac` | Admin de Odoo | Catálogo de PAC disponibles + URLs por ambiente |
| `dgi.web.service` | Admin de Odoo | Credenciales de una empresa para un PAC × ambiente |
| `res.company.l10n_pa_ws_environment_id` | Admin de Odoo | Puntero a cuál config está activa ahora |

**Regla de oro:** Las URLs del WS son propiedad del PAC, no de la empresa.
Si HKA cambia su URL de testing, se actualiza en `dgi.pac` y todas las empresas
quedan actualizadas automáticamente.

---

### Modelo 1 — `dgi.pac` · Catálogo de PAC (`models/dgi_pac.py` — archivo nuevo)

```python
class DgiPac(models.Model):
    _name = 'dgi.pac'
    _description = 'Proveedor Autorizado Calificado (PAC) — FEL Panamá'
    _order = 'name'

    name              # Char  required — Nombre comercial  ej: "The Factory HKA"
    code              # Char  required — Código técnico    ej: "thefactoryhka"
    country_id        # Many2one('res.country') required — SIEMPRE PA
    wsdl_testing_url  # Char  required — URL WSDL ambiente de pruebas
    wsdl_prod_url     # Char  required — URL WSDL ambiente productivo
    active            # Boolean default=True

    _sql_constraints = [
        ('unique_code', 'UNIQUE(code)', 'El código del PAC debe ser único.'),
    ]
```

**Acceso:** cualquier usuario admin de Odoo puede crear/editar registros de `dgi.pac`.
No requiere acceso técnico al código. Agregar un PAC nuevo = crear un registro aquí.

**Dato inicial obligatorio (`data/dgi_pac_data.xml`):**
```xml
<record id="dgi_pac_thefactoryhka" model="dgi.pac">
    <field name="name">The Factory HKA</field>
    <field name="code">thefactoryhka</field>
    <field name="country_id" ref="base.pa"/>
    <field name="wsdl_testing_url">https://demoemision.thefactoryhka.com.pa/ws/obj/v1.0/Service.svc</field>
    <field name="wsdl_prod_url">https://emision.thefactoryhka.com.pa/ws/obj/v1.0/Service.svc</field>
</record>
```

⚠️ Las URLs exactas de HKA deben copiarse desde el acceso actual al WS antes de
implementar. El campo no puede quedar vacío en el dato inicial.

---

### Modelo 2 — `dgi.web.service` · Credenciales por empresa (`models/dgi_web_service.py` — reemplaza existente)

```python
class DgiWebService(models.Model):
    _name = 'dgi.web.service'
    _description = 'Configuración PAC por empresa — FEL Panamá'
    _order = 'pac_id, environment'

    name           # Char     required — nombre libre  ej: "HKA Testing Q2-2025"
    pac_id         # Many2one('dgi.pac')     required
    company_id     # Many2one('res.company') required  default=env.company
    environment    # Selection[testing|productive] required default='testing'

    # ── Compute — readonly, sin store, sin override ───────────────────────────
    ws_wsdl_url    # Char compute=_compute_ws_wsdl_url  readonly=True
                   # lógica: pac_id.wsdl_testing_url si testing
                   #         pac_id.wsdl_prod_url     si productive

    # ── Credenciales — solo de esta empresa ──────────────────────────────────
    ws_user_fname  # Char required — tokenEmpresa
    ws_token_fname # Char required — tokenPassword

    # ── Presentación ─────────────────────────────────────────────────────────
    pac_footer_text # Char — texto pie de página CAFE (opcional)
    active          # Boolean default=True

    _sql_constraints = [
        (
            'unique_pac_env_company',
            'UNIQUE(company_id, pac_id, environment)',
            'Ya existe una configuración para este PAC y ambiente en esta compañía.',
        ),
    ]

    @api.depends('pac_id', 'environment')
    def _compute_ws_wsdl_url(self):
        for rec in self:
            if not rec.pac_id:
                rec.ws_wsdl_url = False
                continue
            if rec.environment == 'productive':
                rec.ws_wsdl_url = rec.pac_id.wsdl_prod_url
            else:
                rec.ws_wsdl_url = rec.pac_id.wsdl_testing_url

    def _get_zeep_client(self):
        """Instancia zeep.Client desde ws_wsdl_url. Lanza UserError si falla."""
        self.ensure_one()
        if not self.ws_wsdl_url:
            raise UserError(
                f'La configuración "{self.name}" no tiene URL WSDL. '
                f'Verifica que el PAC "{self.pac_id.name}" tenga la URL '
                f'de {self.get_environment_label()} configurada.'
            )
        try:
            return zeep.Client(wsdl=self.ws_wsdl_url)
        except Exception as e:
            raise UserError(
                f'No se pudo conectar al WSDL:\n{self.ws_wsdl_url}\n\nDetalle: {e}'
            )

    def action_test_connection(self):
        """Botón 'Probar conexión': verifica que el WSDL sea accesible."""
        self.ensure_one()
        self._get_zeep_client()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Conexión exitosa',
                'message': (
                    f'WSDL cargado correctamente para "{self.name}" '
                    f'({self.get_environment_label()}).'
                ),
                'type': 'success',
            },
        }

    def get_environment_label(self):
        self.ensure_one()
        return dict(self._fields['environment'].selection).get(
            self.environment, self.environment
        )
```

---

### Modelo 3 — `res.company` · Solo cambia el domain del campo existente

```python
# En res_company.py — solo modificar el domain, nada más
l10n_pa_ws_environment_id = fields.Many2one(
    'dgi.web.service',
    string='Configuración PAC activa',
    domain="[('company_id', '=', id), ('active', '=', True), ('pac_id.country_id.code', '=', 'PA')]",
    help=(
        'Configuración de PAC en uso al emitir documentos FEL. '
        'Cambiar aquí no borra las otras configuraciones guardadas.'
    ),
)
```

---

### Sin cambios — métodos que NO se tocan

| Método | Archivo | Por qué no cambia |
|--------|---------|-------------------|
| `get_wsdl()` | `account_move.py` | Ya lee `company.l10n_pa_ws_environment_id.ws_wsdl_url` |
| `get_tokens()` | `account_move.py` | Ya lee `ws_user_fname` y `ws_token_fname` del mismo campo |
| `_post()` | `account_move.py` | Usa `get_wsdl()` / `get_tokens()` — transparente |
| `l10n_pa_create_dict()` | `account_move.py` | No toca configuración de PAC directamente |

---

### Vistas requeridas

**`views/dgi_pac_views.xml` — archivo nuevo**

Form `dgi.pac`:
- Campos: name, code, country_id, active (toggle)
- Grupo "URLs Web Service":
  - wsdl_testing_url  placeholder="https://..."
  - wsdl_prod_url     placeholder="https://..."

List `dgi.pac`: columnas name, code, country_id, active toggle

**`views/dgi_web_service_views.xml` — reescribir**

Form `dgi.web.service`:
- Header: botón "Probar conexión" → `action_test_connection`
- Grupo "Identificación": name, pac_id, company_id (solo si multicompañía), active toggle
- Grupo "Acceso al Web Service":
  - environment (Selection)
  - ws_wsdl_url (readonly, compute — mostrar como referencia visual)
  - ws_user_fname
  - ws_token_fname (password=True)
- Grupo "Documentos CAFE": pac_footer_text

List `dgi.web.service`: columnas name, pac_id, environment, active toggle

---

### Tests requeridos (`tests/test_dgi_web_service.py` — archivo nuevo)

**`TestDgiPac`**
```
test_pac_creado_con_pais_pa
  → dgi_pac_thefactoryhka.country_id.code == 'PA'

test_codigo_pac_unico
  → crear dos dgi.pac con mismo code lanza IntegrityError

test_wsdl_url_compute_testing
  → config con environment='testing' → ws_wsdl_url == pac_id.wsdl_testing_url

test_wsdl_url_compute_productive
  → config con environment='productive' → ws_wsdl_url == pac_id.wsdl_prod_url

test_wsdl_url_compute_cambia_al_cambiar_environment
  → cambiar environment de testing a productive recalcula ws_wsdl_url

test_wsdl_url_compute_vacio_sin_pac
  → ws_wsdl_url es False cuando pac_id está vacío
```

**`TestDgiWebServiceMultiPAC`**
```
test_multiples_configs_misma_empresa
  → empresa puede tener HKA/testing + HKA/productive guardadas

test_constraint_pac_env_company_unico
  → duplicar (company, pac, environment) lanza excepción

test_distinto_pac_mismo_ambiente_permitido
  → HKA/testing + WebPOS/testing en misma empresa → OK (no viola constraint)

test_active_false_excluye_de_busqueda_normal
  → config.active=False no aparece en search([])

test_get_zeep_client_sin_wsdl_lanza_user_error
  → pac_id con wsdl_testing_url vacío → UserError al llamar _get_zeep_client()

test_get_zeep_client_error_red_lanza_user_error
  → mock zeep.Client lanzando Exception → UserError con mensaje de conexión

test_get_zeep_client_retorna_client_cuando_ok
  → mock exitoso → verifica que zeep.Client recibió la URL correcta

test_action_test_connection_retorna_notification_success
  → mock exitoso → result['tag'] == 'display_notification', type == 'success'

test_action_test_connection_sin_wsdl_lanza_user_error
  → pac con url vacía → UserError al presionar botón
```

**`TestCompanyDomainPAC`**
```
test_domain_filtra_solo_pais_pa
  → config de PAC con country_id != PA no aparece en domain de company

test_domain_filtra_solo_empresa_actual
  → config de otra company no aparece en domain

test_cambiar_config_activa_no_borra_otras
  → cambiar l10n_pa_ws_environment_id → las demás configs siguen existiendo

test_get_tokens_lee_de_config_activa
  → move.company_id.l10n_pa_ws_environment_id.ws_user_fname == credencial correcta
```

---

### Archivos a crear / modificar

| Acción | Archivo |
|--------|---------|
| CREAR | `models/dgi_pac.py` |
| MODIFICAR | `models/dgi_web_service.py` (reescribir completo) |
| MODIFICAR | `models/res_company.py` (solo domain del campo existente) |
| MODIFICAR | `models/__init__.py` (agregar `from . import dgi_pac`) |
| CREAR | `views/dgi_pac_views.xml` |
| MODIFICAR | `views/dgi_web_service_views.xml` (reescribir completo) |
| CREAR | `data/dgi_pac_data.xml` (registro HKA con URLs reales) |
| MODIFICAR | `__manifest__.py` (agregar dgi_pac_data.xml en data[], dgi_pac_views.xml en views[]) |
| CREAR | `tests/test_dgi_web_service.py` |
| MODIFICAR | `tests/__init__.py` (agregar import) |

---

### Script de migración (solo si hay datos previos en producción)

Si `dgi.web.service` ya tiene registros, `pac_id NOT NULL` requiere migración previa.
Archivo: `migrations/18.0.1.1.0/pre-migrate.py`

```python
def migrate(cr, version):
    # Primero asegura que dgi_pac exista con HKA
    cr.execute("""
        INSERT INTO dgi_pac (name, code, active)
        VALUES ('The Factory HKA', 'thefactoryhka', true)
        ON CONFLICT (code) DO NOTHING
    """)
    # Luego asigna ese PAC a todos los registros huérfanos
    cr.execute("""
        UPDATE dgi_web_service ws
        SET pac_id = dp.id
        FROM dgi_pac dp
        WHERE dp.code = 'thefactoryhka'
          AND ws.pac_id IS NULL
    """)
```

---

*Versión: Mayo 2026 · Modelo multi-PAC definitivo · l10n_pa_edi v18.0.1.1.0*

---

## BACKLOG PRIORIZADO

| Prioridad | Tarea | Archivo(s) |
|-----------|-------|-----------|
| 🔴 ALTA | **Corregir mapeo `tipoDocumento`** en `l10n_pa_create_dict()` | `account_move.py` |
| 🔴 ALTA | **Implementar retenciones DGI**: modelo `account.move.dgi.retencion`, campo `retencion_ids` en `account.move`, bloque en `l10n_pa_create_dict()`, vista en tab SFEP | `account_move_dgi_retencion.py` (nuevo), `account_move.py`, views |
| 🔴 ALTA | Implementar `EstadoDocumento()` + `action_check_estado_fe()` + botón vista | `account_move.py`, views |
| 🔴 ALTA | Implementar `AnulacionDocumento()` + wizard motivo | `account_move.py`, wizard nuevo |
| 🟡 MEDIA | Implementar `FoliosRestantes()` en config empresa | `res_company.py`, views |
| 🟡 MEDIA | Persistir `afiliadoFE` en `res.partner` | `res_partner.py` |
| 🟡 MEDIA | Eliminar doble llamada a `_l10n_pa_validate_dgi_payments()` en `_post()` | `account_move.py` |
| 🟡 MEDIA | Mover `l10n_pa_fel_estado` de variable local a campo del modelo | `account_move.py` |
| 🟢 BAJA | Eliminar `validar_ruc_panama()` y código comentado en `onchange_customer_type` | `res_partner.py` |
| 🟢 BAJA | Desanclar `codigoSucursalEmisor` y `puntoFacturacionFiscal` hardcodeados | múltiples |
| 🟢 BAJA | Evaluar y limpiar `afip_errors.py`, `l10n_ar_afipws_connection.py` | `models/` |
| 🟢 BAJA | Tests para `tipoDocumento`, `EstadoDocumento`, `AnulacionDocumento`, `FoliosRestantes` | `tests/` |
| ⛔ NO TOCAR | `puntoFacturacionFiscal`, `naturalezaOperacion`, `destinoOperacion` viven en `res.partner.def.fields` pero arquitecturalmente pertenecen a `account.journal`. **NO migrar** hasta tener plan con script SQL + módulo de migración dedicado. | `res_partner_default_fields.py` |

---

*Generado: Mayo 2026 · Basado en código real de `l10n_pa_edi` v18.0.1.0.1 · WS docs: felwiki.thefactoryhka.com.pa*