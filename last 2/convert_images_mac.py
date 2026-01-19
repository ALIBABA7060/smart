import os
from PIL import Image

folder = "students_db"
image_extensions = ('.jpg', '.jpeg', '.png')

for file in os.listdir(folder):
    if file.lower().endswith(image_extensions):
        img_path = os.path.join(folder, file)
        try:
            with Image.open(img_path) as img:
                original_mode = img.mode
                img = img.convert("RGB")  # Force 8-bit RGB
                img.save(img_path)
            print(f"✅ Converted {file}: {original_mode} -> RGB")
        except Exception as e:
            print(f"❌ Failed to convert {file}: {e}")

print("✅ All images processed successfully!")
