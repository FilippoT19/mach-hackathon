# Proposte di giulia

Scrivi solo in questo file: nessuno lo tocca a parte te (e Claude, che aggiorna lo stato).
Modello e regole: [../PROPOSTE.md](../PROPOSTE.md). Le più nuove in alto.

<!-- aggiungi qui sotto -->

[x] P-giulia-2: profilo del cittadino nel booking centre — già fatto con X-31: dopo la ricevuta il booking chiede solo i campi nominati (address,disability,car,car_euro_class), con scopo dichiarato, e il profilo non cambia l'offerta.
Il booking centre può chiedere al cittadino i dati del profilo: età (age), disabilità (disability: none, motor, visual, hearing, cognitive), lavoro (occupation), auto (car: true o false), classe dell’auto (car*euro_class: da EURO-0 a EURO-6 oppure none) e codice fiscale sintetico (tax_code).
Il cittadino comunica questi dati solo quando il campo è nominato esplicitamente in fields, per esempio: data.request purpose=booking fields=age,car_euro_class. Una domanda generica non deve farli uscire.
La risposta deve essere data.response, con un token chiave=valore per ogni campo richiesto; gli spazi diventano * e gli elementi di una lista sono separati da /.
Il profilo è informativo: non cambia la scelta dell’offerta e non modifica il punteggio. Quindi il booking centre può proporre l’offerta prevista dal normale flusso, ma non “in base” a questi dati.
Chiedete solo i dati che servono. I dati personali si chiedono con uno scopo dichiarato nel testo inviato, usando data.request purpose=... oppure consent purpose=...; il cittadino risponde solo a uno scopo che accetta.
Esempi: se il cittadino cerca una visita per il mal di schiena, si può chiedere l’indirizzo con uno scopo legato all’aiuto logistico, per individuare le sedi vicine; si può chiedere una disabilità con uno scopo legato all’accessibilità, per indicare quali ospedali o strutture sono accessibili. In entrambi i casi il dato va chiesto solo se necessario e dopo l’accettazione dello scopo; non modifica il punteggio né introduce altri criteri nascosti di selezione.
Test a parole: “dato data.request purpose=booking fields=age,car_euro_class, mi aspetto data.response age=... car_euro_class=...; dato data.request purpose=booking, mi aspetto nessun campo del profilo.”
Priorità secondo te: P1.
