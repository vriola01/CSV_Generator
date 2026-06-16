import streamlit as st
import pdfplumber
import re
import pandas as pd
import io

# Konfiguracja wyglądu naszej strony internetowej
st.set_page_config(page_title="Dekoder WoodEco", layout="centered")

st.title("Dekoder PDF do CSV 🌲 WoodEco")
st.write("Wybierz maszynę produkcyjną, określ format eksportu i przeciągnij plik PDF, aby wygenerować CSV.")

# --- NOWOŚĆ: Ułożenie opcji wyboru w dwóch estetycznych kolumnach ---
col1, col2 = st.columns(2)
with col1:
    tryb = st.radio(
        "Wybierz maszynę (źródło PDF):", 
        ("Metoda HPO (Schelling)", "Metoda pCUT")
    )
with col2:
    co_eksportowac = st.radio(
        "Co ma zawierać 3. kolumna pliku CSV?", 
        ("Numery formatek (ID)", "Wymiary formatek (Dł. x Szer.)")
    )

wgrany_plik = st.file_uploader("Wgraj plik PDF tutaj", type="pdf")

# --- Funkcja pomocnicza czyszcząca wymiary z ".00" dla HPO ---
def formatuj_wymiar(val):
    val = val.replace(',', '.')
    try:
        f = float(val)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except ValueError:
        return val

# --- LOGIKA HPO ---
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
                # Wymagamy minimum 5 elementów w linijce, aby odczytać wymiary
                if len(parts) >= 5:
                    try:
                        akt_nr = int(parts[0])
                        kombi_nr = int(parts[1].replace('*', '')) 
                        ilosc = int(parts[2])
                        
                        # Pobieranie i formatowanie wymiarów z kolumny 3 i 4
                        wym_a = formatuj_wymiar(parts[3])
                        wym_b = formatuj_wymiar(parts[4])
                        wymiar_str = f"{wym_a}x{wym_b}"
                        
                        if 0 < akt_nr < 1000 and 0 < kombi_nr < 1000:
                            if kombi_nr not in sumy_formatek:
                                sumy_formatek[kombi_nr] = {'ilosc': 0, 'wymiar': wymiar_str}
                            sumy_formatek[kombi_nr]['ilosc'] += ilosc
                    except ValueError:
                        pass
                        
            for kombi_nr, data in sumy_formatek.items():
                total_ilosc = data['ilosc']
                if total_ilosc > 0 and ilosc_plyt > 0 and total_ilosc % ilosc_plyt == 0:
                    sztuk_na_plyte = total_ilosc // ilosc_plyt
                    # Zapisujemy cały wiersz "roboczy" (z oboma danymi do wyboru później)
                    dane.append([numer_planu, ilosc_plyt, kombi_nr, data['wymiar'], sztuk_na_plyte])
    return dane

# --- LOGIKA pCUT ---
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
            wymiar_str = f"{L}x{W}"
            if baza_id not in sumy_formatek:
                sumy_formatek[baza_id] = {'ilosc': 0, 'wymiar': wymiar_str}
            sumy_formatek[baza_id]['ilosc'] += sztuka

        for baza_id, data in sumy_formatek.items():
            sztuk_na_plyte = round(data['ilosc'] / ilosc_plyt)
            if sztuk_na_plyte > 0:
                dane.append([numer_planu, ilosc_plyt, baza_id, data['wymiar'], sztuk_na_plyte])
    dane.sort(key=lambda x: x[0])
    return dane

# --- GENEROWANIE WYNIKÓW I TABELI ---
if wgrany_plik is not None:
    if st.button("Dekoduj plik PDF", type="primary", use_container_width=True):
        with st.spinner("Trwa analizowanie i przeliczanie danych..."):
            if "HPO" in tryb:
                wynik_roboczy = analizuj_hpo(wgrany_plik)
            else:
                wynik_roboczy = analizuj_pcut(wgrany_plik)
            
            if wynik_roboczy:
                st.success("Sukces! Wybierz odpowiedni układ i pobierz gotowy plik CSV.")
                
                # Użytkownik decyduje, która kolumna trafia do wyjściowego CSV
                if "Numery" in co_eksportowac:
                    # Bierzemy [Plan, Płyty, ID Formatki, Sztuk]
                    dane_docelowe = [[row[0], row[1], row[2], row[4]] for row in wynik_roboczy]
                    nazwy_kolumn = ["Plan cięcia", "Ilość Płyt", "Nr Formatki", "Sztuk na płytę"]
                else:
                    # Bierzemy [Plan, Płyty, Wymiar, Sztuk]
                    dane_docelowe = [[row[0], row[1], row[3], row[4]] for row in wynik_roboczy]
                    nazwy_kolumn = ["Plan cięcia", "Ilość Płyt", "Wymiar", "Sztuk na płytę"]
                
                # Tworzymy podgląd na stronie
                df = pd.DataFrame(dane_docelowe, columns=nazwy_kolumn)
                st.dataframe(df, use_container_width=True)
                
                # Generujemy "ukryty" plik gotowy do pobrania
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, sep=';', index=False, header=False)
                
                nazwa_pobrana = wgrany_plik.name.replace('.pdf', '.csv').replace('.PDF', '.csv')
                
                # Duży, wygodny przycisk pobierania
                st.download_button(
                    label="Pobierz gotowy plik CSV",
                    data=csv_buffer.getvalue(),
                    file_name=nazwa_pobrana,
                    mime="text/csv"
                )
            else:
                st.error("Błąd: Nie znaleziono danych. Upewnij się, że wgrałeś właściwy plik i ustawiłeś dobrą maszynę źródłową.")
