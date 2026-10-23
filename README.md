# UW Wildcards

Acordeón para Forge Neo. Antes de generar:

- quita un marcador final `[W:H]` y ajusta ancho y alto al presupuesto de megapíxeles
- descarga las LoRA del manifiesto que el prompt pida y aún no estén en disco

Los ficheros van a la carpeta de LoRA configurada en Forge, dentro de `UWModularWildcards/`. El tag queda como `<lora:UWModularWildcards/…:peso>`.

La clave de API es la de CivitAI Browser Neo (`Personal CivitAI API key`). Si esa está vacía, se usa la de Settings → UW Wildcards.

## Instalar

En Forge: Extensions → Install from URL, con la URL de este repositorio. Apply and restart UI.

No forma parte de la semilla de docker-neo (`.no-seed`).

## Probar

```sh
python3 -m unittest tests.test_api_key tests.test_aspect tests.test_lora_fetch -v
```
