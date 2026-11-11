from io import BytesIO

from PIL import Image


def encoded(*, format_name: str = "PNG", size: tuple[int, int] = (20, 10)) -> bytes:
    with Image.new("RGBA", size, (255, 0, 0, 128)) as image:
        output = BytesIO()
        if format_name == "JPEG":
            converted = image.convert("RGB")
            try:
                converted.save(output, format=format_name)
            finally:
                converted.close()
        else:
            image.save(output, format=format_name)
        return output.getvalue()
