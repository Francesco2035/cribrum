# config/topic_stopwords.yaml

Parole escluse dalle **parole chiave** degli argomenti: non descrivono un tema. Gli embedding non ne sono toccati, perché le finestre vengono codificate con il testo intero.

- **Inglese**: arriva già dalla lista di scikit-learn (`ENGLISH_STOP_WORDS`) e non va ripetuto qui.
- `italian`: articoli, preposizioni articolate, pronomi, verbi ausiliari e modali, avverbi frequenti.
- `elisions`: quello che resta di "all'esame", "dell'anno" o "c'è" quando l'apostrofo spezza la parola.
- `chat`: saluti, ringraziamenti, intercalari ("raga", "lol", "haha") e parole inglesi frequenti nelle chat ma assenti dalla lista di scikit-learn ("guys", "gonna").

I nomi dei gruppi (`italian`, `elisions`, `chat`) servono solo a leggere il file: vengono uniti in un'unica lista. Si possono aggiungere gruppi nuovi. Cambiare la lista cambia l'hash dei risultati di `discover`, quindi produce una cartella nuova.
