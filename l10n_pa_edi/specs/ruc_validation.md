# Spec: Consulta RUC/DV — l10n_pa_edi

## Contexto
Consulta al WebService de la DGI panameña para obtener el DV,
razón social y estado de afiliación FE de un contribuyente.

## Decisión de arquitectura
No existe validación de formato local. El WS de la DGI es el
único árbitro. `validar_ruc_panama()` está deprecada y debe
eliminarse en la próxima limpieza.

## WS: ConsultarRucDV

### Request
| Campo         | Tipo   | Descripción                        |
|---------------|--------|------------------------------------|
| tokenEmpresa  | string | Provisto por proveedor tecnológico |
| tokenPassword | string | Provisto por proveedor tecnológico |
| tipoRuc       | string | '1' Natural / '2' Jurídico         |
| ruc           | string | RUC del contribuyente              |

### Response (código 200 — éxito)
| Campo             | Tipo   | Se mapea a                  |
|-------------------|--------|-----------------------------|
| codigo            | string | Evaluación éxito/error      |
| infoRuc.ruc       | string | (no usado actualmente)      |
| infoRuc.tipoRuc   | string | (no usado actualmente)      |
| infoRuc.dv        | string | res.partner.l10n_pa_edi_dv  |
| infoRuc.razonSocial| string| res.partner.name            |
| infoRuc.afiliadoFE| string | res.partner.l10n_pa_edi_afiliado_fe (pendiente) |
| mensaje           | string | (no usado actualmente)      |
| resultado         | string | (no usado actualmente)      |

### Códigos de respuesta conocidos
| Código | Mensaje                                          |
|--------|--------------------------------------------------|
| 200    | Éxito — procesar infoRuc                         |
| 100    | El token del emisor es inválido                  |
| 101    | Error al validar el certificado de transmisión   |
| 102    | Contribuyente no inscrito                        |
| 201    | Error al procesar la consulta                    |
| 202    | Error al recibir la respuesta de la DGI          |
| N/A    | Error desconocido (fallback)                     |

## Comportamiento de check_ruc()

1. Si `vat` está vacío → UserError inmediato, sin llamar al WS
2. Llama a ConsultarRucDV con tipoRuc según l10n_pa_edi_tipo_contribuyente
3. Si código != '200' → UserError con mensaje del result_map
4. Si código == '200':
   - Actualiza `name` con razonSocial (si existe)
   - Actualiza `l10n_pa_edi_dv` con dv (si existe)
   - Marca `l10n_pa_edi_checked = True`
   - Postea respuesta completa en el chatter

## Comportamiento de onchange_customer_type()

| customer_type | tipo_contribuyente |
|---------------|--------------------|
| '01' Contribuyente    | '2' Jurídico   |
| '02' Consumidor Final | '1' Natural    |
| '03' Gobierno         | '2' Jurídico   |
| '04' Extranjero       | '' (vacío)     |

## Deuda técnica documentada

- [ ] validar_ruc_panama() — eliminar, código muerto
- [ ] afiliadoFE no se persiste — campo pendiente en res.partner
- [ ] infoRuc.ruc y tipoRuc no se verifican contra lo enviado
- [ ] mensaje y resultado del WS se ignoran silenciosamente
- [ ] Código comentado en onchange_customer_type (~línea 120)
- [ ] return comentado en check_ruc() (ventana de diálogo)