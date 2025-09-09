import requests
from bs4 import BeautifulSoup

url = "https://www.atacadao.com.br/arroz-integral-tio-joao-tipo-1-46814-14243/p" # Arroz Tio João

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

print("Buscando informações na URL...")
try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, 'html.parser')

    price_element = soup.find('p', class_='text-2xl text-neutral-500 font-bold')

    if price_element:
        price = price_element.get_text()
        print("---------------------------------")
        print(f"Preço encontrado: {price}")
        print("---------------------------------")
    else:
        print("Elemento do preço não encontrado. A estrutura do site pode ter mudado.")

except requests.exceptions.RequestException as e:
    print(f"Erro ao acessar a página: {e}")