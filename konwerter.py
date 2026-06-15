import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

# Konfiguracja wyglądu naszej strony internetowej
st.set_page_config(page_title="CSV Generator", layout="centered")

st.title("CSV Generator")
st.write("Wybierz program optymalizacyjny i przeciągnij plik PDF, aby wygenerować CSV.")

# 1. Wybór metody za pomocą przełącznika (Radio button)
tryb = st.radio("Optymalizator:", ("HPO (Schelling)", "pCUT"))

# 2. Miejsce na "Drag & Drop" prosto w przeglądarce!
wgrany_plik = st.file_uploader("Wgraj plik PDF tutaj", type="pdf")

# --- NASZA LOGIKA HPO ---
def analizuj_hpo(plik_pdf):
    dane = []
    with pdfplumber.open(plik_pdf) as pdf:
        for strona in pdf.pages:
            tekst = strona.extract_text()
            if not tekst: continue
                
            plan_match = re.search(r"Formatek w rozkr[^\d]*(\d+)", tekst, re.IGNORECASE)
            if not plan_match: continue
            numer_planu = int(plan_match.group(1))
            
            plyty_match = re.search(r"(\d+)\s*P[lł]yt", tekst, re.IGNORECASE)
            if not plyty_match: continue
            ilosc_plyt = int(plyty_match.group(1))
            
            if "wyprodukowano" in tekst:
                tabela = tekst.split("wyprodukowano")[-1]
            elif "Akt.Nr." in tekst:
                tabela = tekst.split("Akt.Nr.")[-1]
            else:
                tabela = tekst
                
            if "Pakietow" in tabela:
                tabela = tabela.split("Pakietow")[0]
                
            sumy_formatek = {}
            for line in tabela.split('\n'):
                parts = line.strip().split()
                if len(parts) >= 3:
                    try:
                        akt_nr = int(parts[0])
                        kombi_nr = int(parts[1].replace('*', '')) 
                        ilosc = int(parts[2])
                        if 0 < akt_nr < 1000 and 0 < kombi_nr < 1000:
                            if kombi_nr not in sumy_formatek:
                                sumy_formatek[kombi_nr] = 0
                            sumy_formatek[kombi_nr] += ilosc
                    except ValueError:
                        pass
                        
            for kombi_nr, total_ilosc in sumy_formatek.items():
                if total_ilosc > 0 and ilosc_plyt > 0 and total_ilosc % ilosc_plyt == 0:
                    sztuk_na_plyte = total_ilosc // ilosc_plyt
                    dane.append([numer_planu, ilosc_plyt, kombi_nr, sztuk_na_plyte])
    return dane

# --- NASZA LOGIKA pCUT ---
def analizuj_pcut(plik_pdf):
    dane = []
    wymiary_do_id = {} 
    plany_surowe = []
    with pdfplumber.open(plik_pdf) as pdf:
        for strona in pdf.pages:
            tekst = strona.extract_text()
            if not tekst or "Plan sztaplowania" not in tekst: continue

            plan_match = re.search(r'(\d+)\s*\(\s*\d+\s*\)', tekst)
            if not plan_match: continue
            numer_planu = int(plan_match.group(1))

            plyty_match = re.search(r'(\d+)\s*P[lł]yt', tekst, re.IGNORECASE)
            if not plyty_match: continue
            ilosc_plyt = int(plyty_match.group(1))

            czesci = []
            for line in tekst.split('\n'):
                line = line.strip()
                m = re.search(r'^\*?(\d+)\s+(\d{3,4})\s+(\d{3,4})\s*(?:[A-Za-z]+\s*)?(\d+)', line)
                if m:
                    fmt_id = int(m.group(1))
                    L = int(m.group(2))
                    W = int(m.group(3))
                    sztuka_calkowita = int(m.group(4))
                    if 0 < fmt_id < 1000 and sztuka_calkowita > 0:
                        czesci.append((fmt_id, L, W, sztuka_calkowita))
                        wymiar = (L, W)
                        if wymiar not in wymiary_do_id:
                            wymiary_do_id[wymiar] = fmt_id
                        else:
                            wymiary_do_id[wymiar] = min(wymiary_do_id[wymiar], fmt_id)

            plany_surowe.append({'numer_planu': numer_planu, 'ilosc_plyt': ilosc_plyt, 'czesci': czesci})

    for plan in plany_surowe:
        numer_planu = plan['numer_planu']
        ilosc_plyt = plan['ilosc_plyt']
        sumy_formatek = {}
        for fmt_id, L, W, sztuka in plan['czesci']:
            baza_id = wymiary_do_id[(L, W)]
            sumy_formatek[baza_id] = sumy_formatek.get(baza_id, 0) + sztuka

        for baza_id, total_sztuka in sumy_formatek.items():
            sztuk_na_plyte = round(total_sztuka / ilosc_plyt)
            if sztuk_na_plyte > 0:
                dane.append([numer_planu, ilosc_plyt, baza_id, sztuk_na_plyte])
    dane.sort(key=lambda x: x[0])
    return dane

# --- GENEROWANIE WYNIKÓW ---
if wgrany_plik is not None:
    if st.button("Dekoduj plik PDF", type="primary"):
        with st.spinner("Przetwarzam dane..."):
            if "HPO" in tryb:
                wynik = analizuj_hpo(wgrany_plik)
            else:
                wynik = analizuj_pcut(wgrany_plik)
            
            if wynik:
                st.success("Gotowe! Możesz pobrać plik CSV lub podejrzeć dane poniżej.")
                
                # Używamy Pandas do stworzenia ładnej tabeli HTML
                df = pd.DataFrame(wynik, columns=["Plan cięcia", "Ilość Płyt", "Nr Formatki", "Sztuk na płytę"])
                st.dataframe(df, use_container_width=True)
                
                # Przygotowanie pliku CSV w pamięci
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, sep=';', index=False, header=False)
                
                nazwa_pobrana = wgrany_plik.name.replace('.pdf', '.csv').replace('.PDF', '.csv')
                
                # Przycisk do pobierania CSV z poziomu przeglądarki
                st.download_button(
                    label="Pobierz plik CSV",
                    data=csv_buffer.getvalue(),
                    file_name=nazwa_pobrana,
                    mime="text/csv"
                )
            else:
                st.error("Błąd: Nie znaleziono danych. Upewnij się, że wgrałeś właściwy plik i wybrałeś dobrą maszynę.")