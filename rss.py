
import re
import json
import urllib.request
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.molins.es"

WEB_INVERSORES = (
    BASE_URL + "/inversores/accionistas-inversores/"
)

WEB_ACTUALIDAD = BASE_URL + "/actualidad/"
WEB_BLOG = BASE_URL + "/blog/"

OUTPUT_FILE = Path("molins-inversores.xml")

RSS_URL = (
    "https://plis2100.github.io/"
    "rss-molins-inversores/molins-inversores.xml"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
    ),
    "Accept": "text/html,application/xml,application/json,*/*",
}


def descargar(url):
    solicitud = urllib.request.Request(
        url, headers=HEADERS
    )
    with urllib.request.urlopen(
        solicitud, timeout=60
    ) as respuesta:
        return respuesta.read()


def fecha_iso(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(
            valor.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def obtener_fecha(enlace, titulo):
    coincidencia = re.search(
        r"(\d{2})[/-](\d{2})[/-](\d{4})",
        titulo,
    )

    if coincidencia:
        dia, mes, anio = coincidencia.groups()
        try:
            return datetime(
                int(anio), int(mes), int(dia),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    coincidencia = re.search(
        r"/uploads/(\d{4})/(\d{2})/",
        enlace,
    )

    if coincidencia:
        anio, mes = coincidencia.groups()
        try:
            return datetime(
                int(anio), int(mes), 1,
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    return None


def crear_item(titulo, enlace, fecha=None,
               categoria="Actualidad", anio=""):
    return {
        "titulo": titulo.strip(),
        "enlace": enlace,
        "fecha": fecha,
        "categoria": categoria,
        "anio": anio,
    }


def descargar_documentos():
    contenido = descargar(WEB_INVERSORES)
    soup = BeautifulSoup(contenido, "html.parser")

    documentos = []
    encontrados = set()

    for elemento in soup.select(
        "li.item-agenda-inversor a"
    ):
        enlace = elemento.get("href", "").strip()
        titulo = elemento.get_text(" ", strip=True)
        anio = elemento.get("data-date", "").strip()

        if not enlace or not titulo:
            continue

        enlace = urljoin(BASE_URL, enlace)

        if enlace in encontrados:
            continue

        encontrados.add(enlace)

        documentos.append(
            crear_item(
                titulo,
                enlace,
                obtener_fecha(enlace, titulo),
                "Agenda del inversor",
                anio,
            )
        )

    return documentos


def descargar_actualidad_api():
    """
    Consulta las publicaciones de WordPress.
    Se utiliza como fuente complementaria.
    """
    noticias = []
    encontrados = set()

    for pagina in range(1, 6):
        url = (
            BASE_URL
            + "/wp-json/wp/v2/posts"
            + f"?per_page=100&page={pagina}"
            + "&_fields=link,title,date,date_gmt"
        )

        try:
            datos = json.loads(
                descargar(url).decode("utf-8")
            )
        except Exception as error:
            print("API WordPress:", error)
            break

        if not isinstance(datos, list) or not datos:
            break

        for entrada in datos:
            enlace = entrada.get("link", "")
            titulo_html = entrada.get(
                "title", {}
            ).get("rendered", "")

            titulo = BeautifulSoup(
                titulo_html, "html.parser"
            ).get_text(" ", strip=True)

            enlace = urljoin(BASE_URL, enlace)

            if not titulo or enlace in encontrados:
                continue

            if urlparse(enlace).netloc not in (
                "www.molins.es", "molins.es"
            ):
                continue

            fecha = fecha_iso(
                entrada.get("date_gmt")
            )

            if fecha is None:
                fecha = fecha_iso(
                    entrada.get("date")
                )

            encontrados.add(enlace)

            noticias.append(
                crear_item(
                    titulo, enlace, fecha,
                    "Actualidad Molins"
                )
            )

    return noticias


def descargar_actualidad_html():
    """
    Extrae enlaces de noticias desde Actualidad.
    También examina las páginas de archivo.
    """
    noticias = []
    encontrados = set()

    paginas = [
        WEB_ACTUALIDAD,
        WEB_BLOG,
    ]

    for numero in range(2, 6):
        paginas.append(
            WEB_ACTUALIDAD + f"page/{numero}/"
        )
        paginas.append(
            WEB_BLOG + f"page/{numero}/"
        )

    for pagina in paginas:
        try:
            contenido = descargar(pagina)
        except Exception as error:
            print("No se pudo leer:", pagina, error)
            continue

        soup = BeautifulSoup(
            contenido, "html.parser"
        )

        for articulo in soup.select(
            "article, .post, .blog-item, "
            ".news-item, .item-noticia"
        ):
            enlace_tag = articulo.select_one(
                "h1 a, h2 a, h3 a, "
                ".entry-title a, a[href*='/blog/']"
            )

            if enlace_tag is None:
                continue

            enlace = urljoin(
                BASE_URL,
                enlace_tag.get("href", "")
            )
            titulo = enlace_tag.get_text(
                " ", strip=True
            )

            if not titulo or enlace in encontrados:
                continue

            if "/blog/" not in enlace:
                continue

            fecha = None

            time_tag = articulo.select_one(
                "time[datetime]"
            )

            if time_tag:
                fecha = fecha_iso(
                    time_tag.get("datetime")
                )

            encontrados.add(enlace)

            noticias.append(
                crear_item(
                    titulo, enlace, fecha,
                    "Actualidad Molins"
                )
            )

    return noticias


def leer_rss_anterior():
    """
    Conserva las noticias anteriores para
    evitar que desaparezcan de Feedly.
    """
    anteriores = []

    if not OUTPUT_FILE.exists():
        return anteriores

    try:
        arbol = ET.parse(OUTPUT_FILE)
    except ET.ParseError:
        return anteriores

    for item in arbol.findall(".//item"):
        titulo = item.findtext("title", "")
        enlace = item.findtext("link", "")
        categoria = item.findtext(
            "category", "Actualidad Molins"
        )
        fecha_texto = item.findtext("pubDate")

        fecha = None

        if fecha_texto:
            try:
                fecha = parsedate_to_datetime(
                    fecha_texto
                )
            except (ValueError, TypeError):
                pass

        if titulo and enlace:
            anteriores.append(
                crear_item(
                    titulo, enlace, fecha, categoria
                )
            )

    return anteriores


def normalizar_enlace(enlace):
    return enlace.split("#")[0].rstrip("/").lower()


def combinar_items(*grupos):
    resultado = {}

    for grupo in grupos:
        for item in grupo:
            clave = normalizar_enlace(
                item["enlace"]
            )

            if clave not in resultado:
                resultado[clave] = item
            else:
                anterior = resultado[clave]

                if (
                    anterior["fecha"] is None
                    and item["fecha"] is not None
                ):
                    anterior["fecha"] = item["fecha"]

    resultado = list(resultado.values())

    resultado.sort(
        key=lambda item: (
            item["fecha"]
            if item["fecha"] is not None
            else datetime(
                1970, 1, 1,
                tzinfo=timezone.utc
            )
        ),
        reverse=True,
    )

    return resultado


def crear_rss(documentos):
    ET.register_namespace(
        "atom",
        "http://www.w3.org/2005/Atom"
    )

    rss = ET.Element("rss", {"version": "2.0"})
    canal = ET.SubElement(rss, "channel")

    ET.SubElement(canal, "title").text = (
        "Molins - Inversores y Actualidad"
    )

    ET.SubElement(canal, "link").text = BASE_URL

    ET.SubElement(canal, "description").text = (
        "Noticias corporativas de Molins, "
        "actualidad, dividendos, juntas "
        "y documentos para inversores."
    )

    ET.SubElement(canal, "language").text = "es"

    ET.SubElement(
        canal, "lastBuildDate"
    ).text = format_datetime(
        datetime.now(timezone.utc)
    )

    atom = ET.SubElement(
        canal,
        "{http://www.w3.org/2005/Atom}link"
    )
    atom.set("href", RSS_URL)
    atom.set("rel", "self")
    atom.set("type", "application/rss+xml")

    for documento in documentos:
        item = ET.SubElement(canal, "item")

        ET.SubElement(
            item, "title"
        ).text = documento["titulo"]

        ET.SubElement(
            item, "link"
        ).text = documento["enlace"]

        ET.SubElement(
            item, "description"
        ).text = documento["titulo"]

        ET.SubElement(
            item, "category"
        ).text = documento["categoria"]

        if documento.get("anio"):
            ET.SubElement(
                item, "category"
            ).text = documento["anio"]

        guid = ET.SubElement(item, "guid")
        guid.set("isPermaLink", "true")
        guid.text = documento["enlace"]

        if documento["enlace"].lower().endswith(
            ".pdf"
        ):
            adjunto = ET.SubElement(
                item, "enclosure"
            )
            adjunto.set(
                "url", documento["enlace"]
            )
            adjunto.set(
                "type", "application/pdf"
            )
            adjunto.set("length", "0")

        if documento["fecha"]:
            ET.SubElement(
                item, "pubDate"
            ).text = format_datetime(
                documento["fecha"]
            )

    ET.indent(rss, space="  ")

    ET.ElementTree(rss).write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    anteriores = leer_rss_anterior()

    try:
        inversores = descargar_documentos()
    except Exception as error:
        print("Error inversores:", error)
        inversores = []

    actualidad_api = descargar_actualidad_api()
    actualidad_html = descargar_actualidad_html()

    actualidad = combinar_items(
        actualidad_api,
        actualidad_html,
    )

    documentos = combinar_items(
        inversores,
        actualidad,
        anteriores,
    )

    if not inversores and not actualidad:
        raise RuntimeError(
            "No se pudieron obtener noticias nuevas. "
            "Se conserva el XML anterior."
        )

    crear_rss(documentos)

    print("RSS actualizada correctamente")
    print("Inversores:", len(inversores))
    print("Actualidad:", len(actualidad))
    print("Total sin duplicados:", len(documentos))


if __name__ == "__main__":
    main()
