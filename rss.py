import re
import urllib.request
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin

WEB_URL = (
    "https://www.molins.es/inversores/"
    "accionistas-inversores/"
)

BASE_URL = "https://www.molins.es"
OUTPUT_FILE = Path("molins-inversores.xml")


def descargar_documentos():
    solicitud = urllib.request.Request(
        WEB_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/124 Safari/537.36"
            ),
            "Accept": "text/html",
        },
    )

    with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
        contenido = respuesta.read()

    soup = BeautifulSoup(contenido, "html.parser")

    documentos = []
    enlaces_encontrados = set()

    for elemento in soup.select(
        "li.item-agenda-inversor a"
    ):
        enlace = elemento.get("href", "").strip()
        titulo = elemento.get_text(" ", strip=True)
        anio = elemento.get("data-date", "").strip()

        if not enlace or not titulo:
            continue

        enlace = urljoin(BASE_URL, enlace)

        if enlace in enlaces_encontrados:
            continue

        enlaces_encontrados.add(enlace)

        documentos.append(
            {
                "titulo": titulo,
                "enlace": enlace,
                "anio": anio,
                "fecha": obtener_fecha(enlace, titulo),
            }
        )

    return documentos


def obtener_fecha(enlace, titulo):
    # Busca una fecha completa en el título.
    coincidencia = re.search(
        r"(\d{2})[/-](\d{2})[/-](\d{4})",
        titulo,
    )

    if coincidencia:
        dia, mes, anio = coincidencia.groups()

        try:
            return datetime(
                int(anio),
                int(mes),
                int(dia),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    # Si no existe una fecha exacta, utiliza el mes
    # en el que el PDF fue subido a la web.
    coincidencia = re.search(
        r"/uploads/(\d{4})/(\d{2})/",
        enlace,
    )

    if coincidencia:
        anio, mes = coincidencia.groups()

        try:
            return datetime(
                int(anio),
                int(mes),
                1,
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass

    return None


def crear_rss(documentos):
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        },
    )

    canal = ET.SubElement(rss, "channel")

    ET.SubElement(canal, "title").text = (
        "Molins – Accionistas e inversores"
    )
    ET.SubElement(canal, "link").text = WEB_URL
    ET.SubElement(canal, "description").text = (
        "Agenda del inversor, dividendos y juntas "
        "de accionistas de Molins"
    )
    ET.SubElement(canal, "language").text = "es"
    ET.SubElement(canal, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc)
    )

    enlace_atom = ET.SubElement(
        canal,
        "{http://www.w3.org/2005/Atom}link",
    )
    enlace_atom.set("href", WEB_URL)
    enlace_atom.set("rel", "self")
    enlace_atom.set("type", "application/rss+xml")

    for documento in documentos:
        elemento = ET.SubElement(canal, "item")

        ET.SubElement(
            elemento,
            "title",
        ).text = documento["titulo"]

        ET.SubElement(
            elemento,
            "link",
        ).text = documento["enlace"]

        ET.SubElement(
            elemento,
            "description",
        ).text = (
            f"{documento['titulo']}. "
            "Documento para accionistas e inversores de Molins."
        )

        ET.SubElement(
            elemento,
            "category",
        ).text = "Agenda del inversor"

        if documento["anio"]:
            ET.SubElement(
                elemento,
                "category",
            ).text = documento["anio"]

        identificador = ET.SubElement(elemento, "guid")
        identificador.set("isPermaLink", "true")
        identificador.text = documento["enlace"]

        if documento["enlace"].lower().endswith(".pdf"):
            adjunto = ET.SubElement(elemento, "enclosure")
            adjunto.set("url", documento["enlace"])
            adjunto.set("type", "application/pdf")
            adjunto.set("length", "0")

        if documento["fecha"]:
            ET.SubElement(
                elemento,
                "pubDate",
            ).text = format_datetime(documento["fecha"])

    ET.indent(rss, space="  ")

    ET.ElementTree(rss).write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    documentos = descargar_documentos()

    if not documentos:
        raise RuntimeError(
            "No se encontraron documentos de inversores de Molins"
        )

    crear_rss(documentos)

    print(
        f"RSS creada correctamente con "
        f"{len(documentos)} documentos"
    )


if __name__ == "__main__":
    main()
