import requests
from bs4 import BeautifulSoup
import os

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    # "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Cookie": "_ga=GA1.1.786068668.1753111239; _sharedID=d7bb0257-0472-4965-83a5-af83d4f49f1f; _sharedID_cst=TyylLI8srA%3D%3D; _cc_id=d7ea4ede8dfabcc3bdc034a720fbadb; _ga_N6W8XF7DXE=GS2.1.s1755013561$o7$g0$t1755013561$j60$l0$h0; _sharedID_last=Tue%2C%2012%20Aug%202025%2015%3A46%3A01%20GMT; cto_bundle=0ol4-F9JTTAwVnRiTzVvcHFVbllYVExwWU1CVlRiaHhqM1AlMkJsQ2hhZVVLbkxtVyUyRk9zbGx3NUFNdVNJRDJCayUyQnAwNWphWEd6RFkySkFGdjFvbUl4ZCUyQjVGMmR4bXRYTmtKeHhsJTJGQ0M1V3AzTEhIRXB4VzFxc0VrSWxOb3NFQ2JOYjNxaGNSSlRTRDgwRXR4OVBRRWZaZmRmdnFBJTNEJTNE; __gads=ID=57041dbf11803236:T=1753111260:RT=1755013564:S=ALNI_MZXBHjiV23Jjs5dYGrq8TrQoyRmog; __gpi=UID=0000116b79eb65d3:T=1753111260:RT=1755013564:S=ALNI_MbKvJ10CrdOPV9RvRjAixpS5QynDA; __Secure-next-auth.callback-url=https%3A%2F%2Fcivitai.com; __Host-next-auth.csrf-token=5777c95c40e157189cd76e2e2a9d034a77052c9f4d7dfb58e9e6f864089f0ec7%7C31949fb39d78197d31c15e40ba028d41c5b87f313d98400d295f23372e0d0b7c; ref_landing_page=%2Fmodels%2F1702547%3FmodelVersionId%3D2240221; civitai-route=2da8068feec31830bc60402117dab99f|bf4092ed2cc1ac81a1918599cbb73e8c; __Secure-civitai-token=eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..cKPsxSI2LreKXxje.x3Z7M0_yxS-DQjOCx_x3W7n1ktUWHaxoC61Yu0sIa0Y8T5-JF3WlhJxI04Rub3W8nmVyCcOHTU1Hg4t_rK0x8w9Bd2yaPopB5jQyxEz02vKWbHVY0T2gL3PaWUM3DdWT_wvQNA4SzJjbuEsQzv7aC3EPYtQpG55kpiA-C06I0cR5UCUA3bZ-MMjtao6a8n-yPCudxB4z30wzKcbjkATaAeImkKUmQeK-c7hIWPVmx66X1SoYrlFYfPHekiL0uaQgsLvDjXx0X61zBltO69hT6MEWiyJxDVm7dI7nma0dmRYLLKR-QQqQPiL6Hj-s-vDTS_DnVWfO6pgrv-9lnoX66tmaLrIuxYTREpEvKVeU-1UteHzMxwz1vlxYS5iNHrQlrAQ9GO_OpDUq8k0ptojELkNAPcSZ1im0PcchzPqUM74hWrDNscRP-YsdycLcEL28pjXAZHy4nKsHtW0hGmtWI6R-tQxj8gghJ6piAvOfAtsKJQpVDU7bRgoDDvl-A5uJxLGZ2C_ZLaaEkX6TsHcml7L4D8amcu9pqcg1dNpccKHeacvFV2IFI_NzLANUQG0_YxV06iwueOMAUYrHQpHskpYoL9LUHZ39zpp9MMFTWdN4WTYe9Epg_-39aAOYqr2X3m8lLQjAhfGo-PSra2UNqwT0UgZf2J0ulhn1Osthi9k2oyLYWwxCIEbgVlXNkFrCGnwqM7UuDS9_gKpsZZZWlx5QlC_kgE9WA3xoVEpQ-zHFjJD-_V_OHaDEGv7XHZiW27mN9__CatrSShWB5ilRJnzy0iglABwh8dow7DXBZJpxnRc7GuBJ9ecERB-qkLWl-KyJB7PBs98KVE27I3Y5kGVvTRYm0xGX6k5voG-gwYbhqPHvnO9z8jl1Lq0tiblS2rlcRgPYQqFV3szfJzlNcB6maPmBTB3jEYYaNkttbhfOqe3P7C43NmkTHgRKfjU8xysKRwmTFLoNCE88BJrwfWptB0ZD24AEC1htJQjsyqb2U3k_b2Om6XDUr7bvYucrAZ6UYblyJ_1BYinFLl0GFBsLECsJ_De509dw1botl5AgP68xkXF6LPWiRcPjiaHUc9t6Q5cVaJOrnNg29kb81gZ1Ix_k4MY7UPTiCs9H4_ccg4lhtNGfwA1_phkT7ncPLBmQQunezmLaoOzSw3ATvyBc7W43nFGg55y_jhmQl2kJscZ7sDvo9qrBIhMclU2Lan2fObjDaoLEIpGSXklTJWKNLl4n8WEAKme_Pl5AuJ7cYxbB6n29zudI2FPqr-b46fG6X9doIYQFoD2DLEPU8jKPWwXH5tiMC8AnSjL87allvgulT9SxSeyS9Mq4cmwiE2ozAi28C78.BQSiMAs-2jePcIyO4VAx1Q",
    "Pragma": "no-cache",
    "Priority": "u=0, i",
    "Sec-CH-UA": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
}

def fetch_page(url):
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None
    
def find_model_type_from_soup(model_page_soup):
    # find tbody.mantine-Table-tbody
    # loop all tr in tbody
    # find first td inner text == "Base Model", then return second td inner text
    tbody = model_page_soup.find('tbody', class_='mantine-Table-tbody')
    if not tbody:
        return None
    
    for tr in tbody.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 2 and tds[0].get_text(strip=True) == "Base Model":
            return tds[1].get_text(strip=True)
    return None

def find_model_type(url):
    soup = fetch_page(url)
    if soup:
        return find_model_type_from_soup(soup)
    return None

if __name__ == "__main__":
    # test_url = "https://civitai.com/models/481234/andromeda-fate-grand-order-xl"
    # model_type = find_model_type(test_url)
    # print(f"Model type for {test_url}: {model_type}")
    
    # do your work here, do not remove above test code
    pass