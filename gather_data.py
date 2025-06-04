import tqdm
import subprocess
import torch
import os

# inclusive range
city_graph = [
    1100,
    2600,
    2700,
    2800,
    2900,
    3000,
    3100,
    5100,
    4100,
    5200,
    4300,
    4400,
    5300,
    4600,
    4700,
    4800,
    4900,
]

def generate_args(city_code: int, town_code: int):
    cmd = rf"""
curl 'http://info.nec.go.kr/electioninfo/electionInfo_report.xhtml' \
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7' \
  -H 'Accept-Language: en-US,en;q=0.9,ko;q=0.8' \
  -H 'Cache-Control: max-age=0' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -b 'WMONID=DXQ3Ey2IUkb; _fwb=1aNaBiOCU84AOC4BTzwKY.1749046886293; JSESSIONID=wyOPbmPFVyjF9SQ6QNA6QJe1xQO1pnpB10TvpuSKJLoyzkchlyizs81dvTIAM9n5.elecapp6_servlet_engine1' \
  -H 'Origin: http://info.nec.go.kr' \
  -H 'Referer: http://info.nec.go.kr/electioninfo/electionInfo_report.xhtml' \
  -H 'Upgrade-Insecure-Requests: 1' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0' \
  --data-raw 'electionId=0020250603&requestURI=%2Felectioninfo%2F0020250603%2Fvc%2Fvccp08.jsp&topMenuId=VC&secondMenuId=VCCP08&menuId=VCCP08&statementId=VCCP08_%231&electionCode=1&cityCode={city_code}&sggCityCode=-1&townCodeFromSgg=-1&townCode={town_code}&sggTownCode=-1&checkCityCode=-1&x=94&y=15' \
  --insecure
"""
    cmd = cmd.replace('\\', '').replace('\n', '')
    return cmd

def fetch_html(city_code: int, town_code: int):
    try:
        cmd = generate_args(city_code, town_code)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        # print(e)
        return None

def fetch_htmls(cache_path = './cache/htmls.pt'):
    if os.path.exists(cache_path):
        htmls = torch.load(cache_path)
    else:
        htmls = []

        for city_code in tqdm.tqdm(city_graph, dynamic_ncols=True, desc='city', leave=False):
            for town_code in tqdm.tqdm(range(city_code + 1, city_code + 100), dynamic_ncols=True, desc='town', leave=False):
                html = fetch_html(city_code, town_code)
                if '검색된 결과가 없습니다' in html:
                    pass
                else:
                    htmls.append((city_code, town_code, html))

        
        os.makedirs('./cache', exist_ok=True)
        torch.save(htmls, cache_path)
    
    for i in range(len(htmls)):
        ccode, tcode, html = htmls[i]
        # html = html.replace('\\t', '\t').replace('\\n', '\n')
        htmls[i] = (ccode, tcode, html)
    
    print('fetched', len(htmls))
    return htmls

from bs4 import BeautifulSoup
import pandas as pd

def get_city_province_and_district_names(html_content):
    """
    Extracts the selected City/Province (시도) and District/City/County (구시군) names
    from the provided HTML content.

    Args:
        html_content (str): The HTML content of the election results page.

    Returns:
        tuple: A tuple containing (city_province_name, district_name).
               Returns (None, None) if the elements or selected options are not found.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    city_province_name = None
    district_name = None

    # Find the select element for City/Province (시도)
    city_code_select = soup.find('select', id='cityCode')
    if city_code_select:
        # Use CSS selector to find an option with the 'selected' attribute
        selected_city_option = city_code_select.select('option[selected]')
        if selected_city_option:
            city_province_name = selected_city_option[-1].get_text(strip=True)

    # Find the select element for District/City/County (구시군)
    town_code_select = soup.find('select', id='townCode')
    if town_code_select:
        selected_town_option = town_code_select.find('option', selected=True)
        if selected_town_option:
            district_name = selected_town_option.get_text(strip=True)

    return city_province_name, district_name

def parse_election_results(html_content):
    """
    Parses the provided HTML content to extract election results for each town.

    Args:
        html_content (str): The HTML content of the election results page.

    Returns:
        pandas.DataFrame: A DataFrame containing the extracted table data,
                          or an empty DataFrame if the table is not found.
    """
    page_city_name, page_town_name = get_city_province_and_district_names(html_content)
    
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the table with id 'table01'
    table = soup.find('table', id='table01')

    if not table:
        print("Error: Table with id 'table01' not found in the HTML.")
        return pd.DataFrame()

    # Extract table headers
    headers = []
    header_rows = table.find('thead').find_all('tr')

    # First row of headers
    first_row_ths = header_rows[0].find_all('th')
    for th in first_row_ths:
        if 'colspan' in th.attrs:
            colspan = int(th['colspan'])
            # For colspan headers, we'll append the sub-headers later
            headers.extend([''] * colspan)
        else:
            headers.append(th.get_text(strip=True).replace('\n', ''))

    # Second row of headers (for colspan columns)
    if len(header_rows) > 1:
        second_row_ths = header_rows[1].find_all('th')
        col_index = 0
        for i, header_val in enumerate(headers):
            if header_val == '':  # This is a colspan placeholder
                # Replace placeholders with actual sub-headers
                for j in range(len(second_row_ths)):
                    if col_index < len(second_row_ths):
                        headers[i + j] = second_row_ths[col_index].get_text(strip=True).replace('\n', ' ')
                        col_index += 1
                    else:
                        break
                break # All sub-headers handled

    # If there are still empty headers (e.g., first few columns without sub-headers), populate them
    # by taking the text from the first row's corresponding th
    current_first_row_th_index = 0
    for i, header_val in enumerate(headers):
        if not header_val:
            # Handle cases where the first row has individual headers and no colspan
            if first_row_ths[current_first_row_th_index].get_text(strip=True):
                headers[i] = first_row_ths[current_first_row_th_index].get_text(strip=True).replace('\n', '')
            current_first_row_th_index += 1
        elif 'colspan' not in first_row_ths[current_first_row_th_index].attrs:
            current_first_row_th_index += 1


    # Adjust headers for "후보자별 득표수" and its sub-columns
    final_headers = []
    # Identify the start of '후보자별 득표수' columns
    candidate_start_index = -1
    for i, header in enumerate(headers):
        if "더불어민주당" in header: # A unique string from the candidate list
            candidate_start_index = i
            break

    if candidate_start_index != -1:
        # Before candidate names
        final_headers.extend(headers[:candidate_start_index])
        # Candidate names and '계' under '후보자별 득표수'
        candidate_headers = []
        for i in range(candidate_start_index, len(headers)):
            if headers[i] == '계': # '계' is part of candidate scores
                candidate_headers.append(headers[i])
                break
            else:
                candidate_headers.append(headers[i])
        final_headers.extend(candidate_headers)
        # After candidate names
        final_headers.extend(headers[candidate_start_index + len(candidate_headers):])
    else:
        final_headers = headers

    # Remove any empty strings that might have been left over due to complex header parsing
    final_headers = ["시도", "구시군"] + [h for h in final_headers if h]

    # Extract table rows
    last_town_name = ""
    table_data = []
    for row in table.find('tbody').find_all('tr'):
        cols = row.find_all('td')
        # Extract text from each cell and strip whitespace
        row_data = [ele.get_text(strip=True) for ele in cols]
        if row_data[0] == "":
            row_data[0] = last_town_name
        else:
            last_town_name = row_data[0]
        row_data = [page_city_name, page_town_name] + row_data
        table_data.append(row_data)

    # Create a Pandas DataFrame
    df = pd.DataFrame(table_data, columns=final_headers)

    # Filter out summary rows like '합계', '거소·선상투표', '관외사전투표', '재외투표', '잘못 투입·구분된 투표지'
    # and also '소계' rows for each town.
    # We want rows where the '읍면동명' is not empty and '투표구명' is empty or not '소계',
    # indicating a specific town's total (excluding the overall summaries).
    # Or where '투표구명' is a specific polling station.

    # Identify rows that represent towns (읍면동명) and their individual polling stations (투표구명)
    filtered_data = []
    current_town = ""
    for row in table_data:
        town_name = row[0]
        polling_station_name = row[1]

        # Conditions to include a row:
        # 1. It's not a global summary row (합계, 거소·선상투표, 관외사전투표, 재외투표, 잘못 투입·구분된 투표지)
        # 2. It's not a "소계" row (which is a sub-total for the town, we'll get the actual polling stations)
        # 3. If '읍면동명' is not empty, it's a new town or a polling station for that town
        # 4. If '읍면동명' is empty, it's a polling station for the current town
        if town_name not in ["합계"]:
            if "소계" not in polling_station_name:
                if town_name: # New town or a polling station under a new town
                    current_town = town_name
                    filtered_data.append(row)
                elif current_town: # Polling station under the current town (읍면동명 is empty)
                    # For polling stations where the town name is empty, fill it with the current_town
                    row[0] = current_town
                    filtered_data.append(row)

    # Re-create DataFrame with filtered data
    df_filtered = pd.DataFrame(filtered_data, columns=final_headers)

    return df_filtered

def fetch_csv(data_path="./data/vote.csv"):
    os.makedirs('./data', exist_ok=True)
    
    if os.path.exists(data_path):
        df = pd.read_csv(data_path)
    else:
        htmls = fetch_htmls()
        
        df = None
        for _, _, html in tqdm.tqdm(htmls, desc='process', leave=False, dynamic_ncols=True):
            df_item = parse_election_results(html)
            if df is None:
                df = df_item
            else:
                df = pd.concat([df, df_item])
        
        df.to_csv(data_path)
    return df

def main():
    df = fetch_csv()
    print(df)

if __name__ == '__main__':
    main()