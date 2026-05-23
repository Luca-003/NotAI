// Scenari demo per testare NotAI end-to-end come un notaio.
// Fonte canonica: demostuff/scenarios.yaml (questo file e' la versione TS
// importabile direttamente dal frontend - sync manuale per ora).

export type DemoParty = {
  role: string;
  kind: "PF" | "PG";
  fiscal_code?: string;
  vat?: string;
  anagrafica: Record<string, unknown>;
};

export type DemoScenario = {
  id: string;
  label: string;
  practice: {
    code: string;
    kind: string;
    title: string;
    description: string;
  };
  act: {
    kind: string;
    title: string;
  };
  workflow_input: {
    template_id: string;
    base_imponibile: number;
    is_prima_casa: boolean;
    parties: DemoParty[];
  };
};

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: "compravendita-prima-casa",
    label: "Compravendita prima casa - appartamento Milano",
    practice: {
      code: `2026/${Math.floor(Math.random() * 9000 + 1000)}`,
      kind: "notarile.compravendita.immobiliare",
      title: "Rossi-Bianchi - compravendita appartamento Via Garibaldi 12, Milano",
      description:
        "Compravendita di unita' immobiliare residenziale categoria A/2 sita in Milano, Via Garibaldi 12, scala A interno 4. Acquisto prima casa agevolato. Trasferimento libero da pesi.",
    },
    act: {
      kind: "notarile.compravendita.immobiliare",
      title: "Atto di compravendita immobiliare prima casa",
    },
    workflow_input: {
      template_id: "notarile.compravendita.immobiliare:v1",
      base_imponibile: 285000,
      is_prima_casa: true,
      parties: [
        {
          role: "venditore",
          kind: "PF",
          fiscal_code: "RSSMRA70A01F205X",
          anagrafica: {
            nome: "Mario",
            cognome: "Rossi",
            data_nascita: "1970-01-01",
            luogo_nascita: "Milano (MI)",
            indirizzo: "Via Garibaldi 12, 20121 Milano",
          },
        },
        {
          role: "acquirente",
          kind: "PF",
          fiscal_code: "BNCLCA85B05H501Y",
          anagrafica: {
            nome: "Luca",
            cognome: "Bianchi",
            data_nascita: "1985-02-05",
            luogo_nascita: "Roma (RM)",
            indirizzo: "Viale Monza 88, 20127 Milano",
          },
        },
      ],
    },
  },
  {
    id: "donazione-genitore-figlio",
    label: "Donazione tra parenti in linea retta",
    practice: {
      code: `2026/${Math.floor(Math.random() * 9000 + 1000)}`,
      kind: "notarile.donazione",
      title: "Verdi - donazione di immobile a figlio Andrea",
      description:
        "Donazione di unita' immobiliare cat. A/3 sita in Roma, Via dei Fori 10. Donante e donatario in linea retta (genitore -> figlio maggiorenne).",
    },
    act: {
      kind: "notarile.donazione",
      title: "Atto di donazione immobiliare",
    },
    workflow_input: {
      template_id: "notarile.donazione:v1",
      base_imponibile: 180000,
      is_prima_casa: false,
      parties: [
        {
          role: "donante",
          kind: "PF",
          fiscal_code: "VRDGPP55C15H501W",
          anagrafica: {
            nome: "Giuseppe",
            cognome: "Verdi",
            data_nascita: "1955-03-15",
            luogo_nascita: "Roma (RM)",
            indirizzo: "Via dei Fori 10, 00184 Roma",
          },
        },
        {
          role: "donatario",
          kind: "PF",
          fiscal_code: "VRDNDR90D20H501T",
          anagrafica: {
            nome: "Andrea",
            cognome: "Verdi",
            data_nascita: "1990-04-20",
            luogo_nascita: "Roma (RM)",
            indirizzo: "Via dei Fori 10, 00184 Roma",
          },
        },
      ],
    },
  },
  {
    id: "costituzione-srl",
    label: "Costituzione SRL con socio unico",
    practice: {
      code: `2026/${Math.floor(Math.random() * 9000 + 1000)}`,
      kind: "notarile.costituzione_srl",
      title: "Acme Tech SRL - costituzione societaria",
      description:
        "Costituzione di societa' a responsabilita' limitata unipersonale. Capitale sociale 15.000 EUR interamente sottoscritto e versato. Oggetto: sviluppo software e consulenza IT.",
    },
    act: {
      kind: "notarile.costituzione_srl",
      title: "Atto costitutivo SRL",
    },
    workflow_input: {
      template_id: "notarile.costituzione_srl:v1",
      base_imponibile: 15000,
      is_prima_casa: false,
      parties: [
        {
          role: "socio_unico",
          kind: "PF",
          fiscal_code: "FRRGPP82E18F205Q",
          anagrafica: {
            nome: "Giuseppe",
            cognome: "Ferrari",
            data_nascita: "1982-05-18",
            luogo_nascita: "Milano (MI)",
            indirizzo: "Via Manzoni 45, 20121 Milano",
          },
        },
      ],
    },
  },
  // ---------------------------------------------------------------------
  // LEGALE - scenari per studio avvocati
  // ---------------------------------------------------------------------
  {
    id: "citazione-recupero-credito",
    label: "Atto di citazione - recupero credito commerciale",
    practice: {
      code: `2026/${Math.floor(Math.random() * 9000 + 1000)}`,
      kind: "legale.contenzioso.civile",
      title: "Alfa Srl c. Beta Srl - recupero credito fatture insolute",
      description:
        "Atto di citazione davanti al Tribunale di Milano per il recupero di credito commerciale derivante da 6 fatture non saldate per fornitura di servizi IT. Valore: 42.500,00 EUR oltre interessi.",
    },
    act: {
      kind: "legale.citazione",
      title: "Atto di citazione recupero credito commerciale",
    },
    workflow_input: {
      template_id: "legale.atto_citazione:v1",
      base_imponibile: 42500,
      is_prima_casa: false,
      parties: [
        {
          role: "attore",
          kind: "PG",
          vat: "12345670156",
          anagrafica: {
            denominazione: "Alfa Servizi Srl",
            sede_legale: "Via Dante 5, 20121 Milano",
            legale_rappresentante: "Marco Conti",
          },
        },
        {
          role: "convenuto",
          kind: "PG",
          vat: "98765432109",
          anagrafica: {
            denominazione: "Beta Commerce Srl",
            sede_legale: "Corso Italia 88, 20122 Milano",
            legale_rappresentante: "Anna Galli",
          },
        },
      ],
    },
  },
  {
    id: "decreto-ingiuntivo-commerciale",
    label: "Ricorso per decreto ingiuntivo - credito documentato",
    practice: {
      code: `2026/${Math.floor(Math.random() * 9000 + 1000)}`,
      kind: "legale.monitorio",
      title: "Gamma Srl - ricorso ex art. 633 cpc per fatture commerciali",
      description:
        "Ricorso per decreto ingiuntivo ex artt. 633 e ss. cpc. Credito documentato da fatture accettate ed estratto conto certificato. Importo richiesto: 18.750,00 EUR oltre interessi e spese.",
    },
    act: {
      kind: "legale.decreto_ingiuntivo",
      title: "Ricorso per decreto ingiuntivo",
    },
    workflow_input: {
      template_id: "legale.decreto_ingiuntivo:v1",
      base_imponibile: 18750,
      is_prima_casa: false,
      parties: [
        {
          role: "ricorrente",
          kind: "PG",
          vat: "11122233344",
          anagrafica: {
            denominazione: "Gamma Forniture Srl",
            sede_legale: "Via Po 14, 10124 Torino",
            legale_rappresentante: "Carla Marchetti",
          },
        },
        {
          role: "ingiunto",
          kind: "PG",
          vat: "55566677788",
          anagrafica: {
            denominazione: "Delta Trade SpA",
            sede_legale: "Via Verdi 22, 10121 Torino",
            legale_rappresentante: "Paolo Sanna",
          },
        },
      ],
    },
  },
  {
    id: "separazione-consensuale",
    label: "Separazione consensuale - negoziazione assistita (DL 132/2014)",
    practice: {
      code: `2026/${Math.floor(Math.random() * 9000 + 1000)}`,
      kind: "legale.famiglia",
      title: "Coniugi Greco-Esposito - separazione consensuale",
      description:
        "Separazione consensuale tra coniugi senza figli minori, realizzata in regime di negoziazione assistita ex DL 132/2014 conv. L. 162/2014. Accordo su mantenimento e assegnazione casa coniugale.",
    },
    act: {
      kind: "legale.separazione_consensuale",
      title: "Accordo di separazione consensuale - negoziazione assistita",
    },
    workflow_input: {
      template_id: "legale.separazione_consensuale:v1",
      base_imponibile: 0,
      is_prima_casa: false,
      parties: [
        {
          role: "coniuge_1",
          kind: "PF",
          fiscal_code: "GRCMRA80A41F205P",
          anagrafica: {
            nome: "Maria",
            cognome: "Greco",
            data_nascita: "1980-01-01",
            luogo_nascita: "Napoli (NA)",
            indirizzo: "Via Roma 5, 80100 Napoli",
          },
        },
        {
          role: "coniuge_2",
          kind: "PF",
          fiscal_code: "SPSGNN78B15F839K",
          anagrafica: {
            nome: "Giovanni",
            cognome: "Esposito",
            data_nascita: "1978-02-15",
            luogo_nascita: "Napoli (NA)",
            indirizzo: "Via Toledo 50, 80132 Napoli",
          },
        },
      ],
    },
  },
];
