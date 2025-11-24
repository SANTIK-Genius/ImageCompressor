import os
import json
import argparse
from pathlib import Path
from PIL import Image, ImageOps
import shutil
from tqdm import tqdm

class ImageCompressor:
    def __init__(self, config_path="config.json"):
        self.config = self.load_config(config_path)
        self.supported_formats = self.config.get("supported_formats", [".jpg", ".jpeg", ".png"])

    def load_config(self, config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️  Конфигурационный файл {config_path} не найден. Используются настройки по умолчанию.")
            return self.get_default_config()
        except json.JSONDecodeError:
            print(f"❌ Ошибка в формате конфигурационного файла {config_path}. Используются настройки по умолчанию.")
            return self.get_default_config()

    def get_default_config(self):
        return {
            "input_folder": "input",
            "output_folder": "output",
            "max_file_size_mb": 1,
            "quality_jpeg": 85,
            "quality_png": 85,
            "resize_enabled": False,
            "max_width": 1920,
            "max_height": 1080,
            "preserve_metadata": True,
            "supported_formats": [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]
        }

    def save_config(self, config_path="config.json"):
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    def get_image_files(self, folder_path):
        folder = Path(folder_path)
        if not folder.exists():
            print(f"❌ Папка {folder_path} не существует!")
            return []

        image_files = []
        for format_ext in self.supported_formats:
            image_files.extend(folder.glob(f"*{format_ext}"))
            image_files.extend(folder.glob(f"*{format_ext.upper()}"))

        return image_files

    def calculate_target_size(self, original_size, max_size_mb):
        return max_size_mb * 1024 * 1024

    def resize_image(self, image, max_width, max_height):
        if image.width <= max_width and image.height <= max_height:
            return image

        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        return image

    def compress_jpeg(self, image, quality, target_size):
        if image.mode != 'RGB':
            image = image.convert('RGB')

        temp_buffer = BytesIO()
        image.save(temp_buffer, format='JPEG', quality=quality, optimize=True)

        current_size = temp_buffer.tell()
        current_quality = quality

        while current_size > target_size and current_quality > 10:
            current_quality -= 5
            temp_buffer = BytesIO()
            image.save(temp_buffer, format='JPEG', quality=current_quality, optimize=True)
            current_size = temp_buffer.tell()

        return temp_buffer.getvalue(), current_quality

    def compress_png(self, image, quality, target_size):
        from io import BytesIO

        temp_buffer = BytesIO()
        image.save(temp_buffer, format='PNG', optimize=True)
        current_size = temp_buffer.tell()

        if current_size > target_size:
            if image.mode != 'RGB':
                image_rgb = image.convert('RGB')
            else:
                image_rgb = image

            jpeg_buffer = BytesIO()
            image_rgb.save(jpeg_buffer, format='JPEG', quality=quality, optimize=True)

            if jpeg_buffer.tell() < current_size:
                return jpeg_buffer.getvalue(), 'JPEG'

        return temp_buffer.getvalue(), 'PNG'

    def compress_image(self, input_path, output_path):
        try:

            with Image.open(input_path) as img:
                original_format = img.format
                original_size = os.path.getsize(input_path)
                target_size = self.calculate_target_size(original_size, self.config["max_file_size_mb"])

                if original_size <= target_size:
                    shutil.copy2(input_path, output_path)
                    return {
                        "status": "skipped",
                        "original_size": original_size,
                        "compressed_size": original_size,
                        "savings_percent": 0,
                        "format": original_format
                    }

                if self.config["resize_enabled"]:
                    img = self.resize_image(img, self.config["max_width"], self.config["max_height"])

                from io import BytesIO

                if original_format in ['JPEG', 'JPG']:
                    compressed_data, quality_used = self.compress_jpeg(
                        img, self.config["quality_jpeg"], target_size
                    )
                    output_format = 'JPEG'

                elif original_format == 'PNG':
                    compressed_data, output_format = self.compress_png(
                        img, self.config["quality_png"], target_size
                    )

                else:

                    buffer = BytesIO()
                    img.save(buffer, format=original_format, optimize=True)
                    compressed_data = buffer.getvalue()
                    output_format = original_format

                with open(output_path, 'wb') as f:
                    f.write(compressed_data)

                compressed_size = os.path.getsize(output_path)
                savings = ((original_size - compressed_size) / original_size) * 100

                return {
                    "status": "compressed",
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "savings_percent": savings,
                    "format": output_format,
                    "original_format": original_format
                }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def process_folder(self):
        input_folder = Path(self.config["input_folder"])
        output_folder = Path(self.config["output_folder"])

        output_folder.mkdir(parents=True, exist_ok=True)

        image_files = self.get_image_files(input_folder)

        if not image_files:
            print("❌ В папке не найдено поддерживаемых изображений!")
            return

        print(f"📁 Найдено {len(image_files)} изображений для обработки")
        print(f"📊 Максимальный размер: {self.config['max_file_size_mb']} МБ")
        print(f"🎯 Качество JPEG: {self.config['quality_jpeg']}%")
        print(f"🎯 Качество PNG: {self.config['quality_png']}%")
        print("─" * 50)

        total_original_size = 0
        total_compressed_size = 0
        processed_count = 0
        skipped_count = 0
        error_count = 0

        for image_path in tqdm(image_files, desc="Обработка изображений", unit="file"):
            output_path = output_folder / image_path.name

            result = self.compress_image(image_path, output_path)

            if result["status"] == "compressed":
                total_original_size += result["original_size"]
                total_compressed_size += result["compressed_size"]
                processed_count += 1

            elif result["status"] == "skipped":
                total_original_size += result["original_size"]
                total_compressed_size += result["compressed_size"]
                skipped_count += 1

            elif result["status"] == "error":
                error_count += 1
                tqdm.write(f"❌ Ошибка при обработке {image_path.name}: {result['error']}")

        print("─" * 50)
        print("📈 РЕЗУЛЬТАТЫ ОБРАБОТКИ:")
        print(f"✅ Успешно сжато: {processed_count} файлов")
        print(f"⏭️  Пропущено: {skipped_count} файлов")
        print(f"❌ Ошибок: {error_count} файлов")

        if processed_count > 0:
            total_savings = ((total_original_size - total_compressed_size) / total_original_size) * 100
            print(f"💾 Экономия места: {total_savings:.1f}%")
            print(f"📦 Исходный размер: {total_original_size / (1024*1024):.1f} МБ")
            print(f"📥 Сжатый размер: {total_compressed_size / (1024*1024):.1f} МБ")
            print(f"💰 Сэкономлено: {(total_original_size - total_compressed_size) / (1024*1024):.1f} МБ")

def main():
    parser = argparse.ArgumentParser(description="Пакетное сжатие изображений")
    parser.add_argument("--input", "-i", help="Входная папка с изображениями")
    parser.add_argument("--output", "-o", help="Выходная папка для сжатых изображений")
    parser.add_argument("--max-size", "-m", type=float, help="Максимальный размер файла в МБ")
    parser.add_argument("--quality", "-q", type=int, help="Качество сжатия (0-100)")
    parser.add_argument("--resize", action="store_true", help="Включить изменение размера")
    parser.add_argument("--width", type=int, help="Максимальная ширина")
    parser.add_argument("--height", type=int, help="Максимальная высота")
    parser.add_argument("--config", "-c", default="config.json", help="Путь к конфигурационному файлу")

    args = parser.parse_args()

    compressor = ImageCompressor(args.config)

    if args.input:
        compressor.config["input_folder"] = args.input
    if args.output:
        compressor.config["output_folder"] = args.output
    if args.max_size:
        compressor.config["max_file_size_mb"] = args.max_size
    if args.quality:
        compressor.config["quality_jpeg"] = args.quality
        compressor.config["quality_png"] = args.quality
    if args.resize:
        compressor.config["resize_enabled"] = True
    if args.width:
        compressor.config["max_width"] = args.width
    if args.height:
        compressor.config["max_height"] = args.height

    compressor.process_folder()

if __name__ == "__main__":
    main()