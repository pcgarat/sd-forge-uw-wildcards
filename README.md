# UW Wildcards

Acordeón para Forge Neo que usa el pack
[UW Modular NSFW Wildcards](https://civitai.red/models/2789815) en txt2img e
img2img. Con el acordeón encendido, al generar:

- el tag `__uw-krea2-nsfw/router/…__` o `__uw-krea2-nsfw/template/…__` elegido
  se convierte en prosa, con los 17 huecos de la plantilla ya resueltos
- un marcador final `[W:H]` se quita y ancho y alto se ajustan al presupuesto de
  megapíxeles
- las LoRA del manifiesto que el prompt pida y aún no estén en disco se
  descargan; el tag queda como `<lora:UWModularWildcards/…:peso>`

Fijar, omitir y regenerar un hueco solo cambian un JSON oculto; no generan ni
piden red. Ese JSON se guarda en los parámetros de la imagen junto al prompt ya
expandido.

El catálogo se lee de la carpeta `wildcards/` del directorio de datos de Forge.
Solo se listan routers y plantillas, no las hojas.

Los pesos van a la carpeta de LoRA configurada en Forge, dentro de
`UWModularWildcards/`.

La clave de API es la de CivitAI Browser Neo (`Personal CivitAI API key`). Si esa
está vacía, se usa la de Settings → UW Wildcards.

## Instalar

En Forge: Extensions → Install from URL, con la URL de este repositorio. Apply and restart UI.

No forma parte de la semilla de docker-neo (`.no-seed`).

## Probar

```sh
python3 -m unittest tests.test_api_key tests.test_aspect tests.test_lora_fetch tests.test_clauses tests.test_catalog -v
```

El corpus YAML del pack no se versiona: los tests usan un fixture mínimo en
`tests/fixtures/`.
