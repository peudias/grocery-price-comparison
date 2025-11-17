from download.download_brasil_atacarejo import run_download_and_convert
from ocr.ocr_cards import run_ocr_for_folder, FOLDER_PNG, OUT_DIR

def pipeline_brasil_atacarejo():
    pngs = run_download_and_convert()
    # if not pngs:
    #     return
    run_ocr_for_folder(FOLDER_PNG, OUT_DIR)

if __name__ == "__main__":
    pipeline_brasil_atacarejo()