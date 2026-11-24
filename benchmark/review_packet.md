# Review packet — 30 draft retrieval questions

**Corpus scope:** 25 openFDA labels; one selected revision per label.
**Answer unit:** distinct Drug ID, not TextChunk.
**Important:** no gold answers are approved by this tool. Review each question against the original openFDA snapshot, including possible additional relevant labels.
**Do not treat an absent contraindication/interaction as evidence of medical safety.**

## Interpretation cautions

- Q01–Q08: query paraphrases are associated with known supporting excerpts. They need a corpus-wide review for additional relevant records.
- Q09–Q15: source candidates can be checked directly against the original openFDA substance_name field, but source metadata is shared with graph construction.
- Q16–Q23: the wording 'verified contraindication' closely matches the annotation labels used to create the graph. These are positive-claim tests, not negation/exclusion tests.
- Q24–Q25: classifications must be checked against the underlying source excerpt. A missing prohibition among reviewed records does not mean a drug combination is safe.
- Q26–Q30: all are conjunctive filters, but most name the primary medicine; they test traversal/AND logic rather than difficult entity resolution.
- Some queries reuse the same exact source chunks, so the test cases are correlated.
- All three retrieval modes must return ranked distinct Drug IDs, with the same test corpus and the same k; disclose that graph filters are supplied to the structured modes rather than inferred from free text.

## Q01 — semantic

Which official drug labels discuss malignant hypertension as a reason not to take a medicine?

- Proposed source candidate(s): WARFARIN SODIUM
- Source-based candidates: manual corpus review required.
- Notes: Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.; Shares a core fact/source with another query; avoid claiming all tests are independent.

  - Evidence `CHUNK:62b5f89f5b15b6ce14e1`: Use in Specific Populations ( 8.1 )] . Warfarin sodium is contraindicated in patients with: Hemorrhagic tendencies or blood dyscrasias Recent or contemplated surgery of the central nervous system or eye, or traumatic surgery resulting in large open surfaces [see Warnings and Precautions ( 5.8 )] Bleeding tendencies associated…

  **Lexical shortlist for further review — NOT gold:**
  - METOPROLOL SUCCINATE (token overlap 2), `CHUNK:e2bc672189550bde7e30`: 2 weeks and monitor the patient. If angina markedly worsens or acute coronary ischemia develops, promptly reinstate metoprolol…
  - WARFARIN SODIUM (token overlap 2), `CHUNK:62b5f89f5b15b6ce14e1`: Use in Specific Populations ( 8.1 )] . Warfarin sodium is contraindicated in patients with: Hemorrhagic tendencies or blood…
  - LOSARTAN POTASSIUM AND HYDROCHLOROTHIAZIDE (token overlap 1), `CHUNK:15f4243e33322e20e3ca`: 1 INDICATIONS AND USAGE Losartan potassium and hydrochlorothiazide tablets are a combination of losartan, an angiotensin II…
  - OMEPRAZOLE (token overlap 1), `CHUNK:8791582bf2b669d5ac06`: young adults to the elderly. The majority of patients presented with rash; however, arthralgia and cytopenia were also reported.…
  - PANTOPRAZOLE SODIUM (token overlap 1), `CHUNK:8c5840739b7e85157b7f`: background risk of major birth defects and miscarriage for the indicated population is unknown. All pregnancies have a background…

## Q02 — semantic

Which official drug labels discuss avoidance of an anti-inflammatory drug around coronary bypass surgery?

- Proposed source candidate(s): NAPROXEN SODIUM
- Source-based candidates: manual corpus review required.
- Notes: Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.

  - Evidence `CHUNK:5d5167e564156b2f6320`: 4 CONTRAINDICATIONS Naproxen sodium tablets are contraindicated in the following patients: Known hypersensitivity (e.g., anaphylactic reactions and serious skin reactions) to naproxen or any components of the drug product [ see Warnings and Precautions (5.7 , 5.9) ] History of asthma, urticaria, or other allergic-type reactions…

  **Lexical shortlist for further review — NOT gold:**
  - IBUPROFEN (token overlap 5), `CHUNK:c926c8460ae22b5548ab`: WARNING: RISK OF SERIOUS CARDIOVASCULAR AND GASTROINTESTINAL EVENTS WARNING: RISK OF SERIOUS CARDIOVASCULAR AND GASTROINTESTINAL…
  - NAPROXEN SODIUM (token overlap 5), `CHUNK:b7d1590dd5e7120658fc`: WARNING: RISK OF SERIOUS CARDIOVASCULAR AND GASTROINTESTINAL EVENTS Cardiovascular Thrombotic Events Nonsteroidal…
  - RIVAROXABAN (token overlap 3), `CHUNK:8dfb922735d9be5e826d`: scheduling patients for spinal procedures. Factors that can increase the risk of developing epidural or spinal hematomas in these…
  - CLOPIDOGREL BISULFATE (token overlap 3), `CHUNK:665757f5509bb26fe73b`: studies, omeprazole was shown to reduce significantly the antiplatelet activity of clopidogrel when given concomitantly or 12…
  - LOSARTAN POTASSIUM AND HYDROCHLOROTHIAZIDE (token overlap 2), `CHUNK:af448a72f6d7c714372e`: 7 DRUG INTERACTIONS Agents increasing serum potassium: Risk of hyperkalemia. ( 7.1 ) Lithium: Risk of lithium toxicity. ( 7.2 )…

## Q03 — semantic

Which official drug labels discuss drug combination with pimozide that is contraindicated?

- Proposed source candidate(s): SERTRALINE HYDROCHLORIDE
- Source-based candidates: manual corpus review required.
- Notes: Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.; Shares a core fact/source with another query; avoid claiming all tests are independent.

  - Evidence `CHUNK:413bd1ff62ee459f93d0`: 4 CONTRAINDICATIONS Sertraline hydrochloride tablets are contraindicated in patients: • Taking, or within 14 days of stopping, MAOIs, (including the MAOIs linezolid and intravenous methylene blue) because of an increased risk of serotonin syndrome [ See Warnings and Precautions (5.2) , Drug Interactions (7.1) ] . • Taking…

  **Lexical shortlist for further review — NOT gold:**
  - OMEPRAZOLE (token overlap 2), `CHUNK:11b953ac8f286df737ce`: 4 CONTRAINDICATIONS • Omeprazole delayed-release capsules are contraindicated in patients with known hypersensitivity reactions…
  - ALOGLIPTIN AND METFORMIN HYDROCHLORIDE (token overlap 2), `CHUNK:1b74e4e70dc0f0a3ba31`: with the severity of renal impairment because metformin is substantially excreted by the kidney. Clinical recommendations based…
  - FLUOXETINE HYDROCHLORIDE (token overlap 2), `CHUNK:cce3883eb0fb4e879474`: 4 CONTRAINDICATIONS When using fluoxetine capsules and olanzapine in combination, also refer to the Contraindications section of…
  - LISINOPRIL (token overlap 2), `CHUNK:9a6e6926a0bb12da3fcb`: 4 CONTRAINDICATIONS Lisinopril tablets are contraindicated in combination with a neprilysin inhibitor (e.g., sacubitril). Do not…
  - SERTRALINE HYDROCHLORIDE (token overlap 2), `CHUNK:413bd1ff62ee459f93d0`: 4 CONTRAINDICATIONS Sertraline hydrochloride tablets are contraindicated in patients: • Taking, or within 14 days of stopping,…

## Q04 — semantic

Which official drug labels discuss bacterial endocarditis listed among situations where a medicine must not be used?

- Proposed source candidate(s): WARFARIN SODIUM
- Source-based candidates: manual corpus review required.
- Notes: Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.; Shares a core fact/source with another query; avoid claiming all tests are independent.

  - Evidence `CHUNK:62b5f89f5b15b6ce14e1`: Use in Specific Populations ( 8.1 )] . Warfarin sodium is contraindicated in patients with: Hemorrhagic tendencies or blood dyscrasias Recent or contemplated surgery of the central nervous system or eye, or traumatic surgery resulting in large open surfaces [see Warnings and Precautions ( 5.8 )] Bleeding tendencies associated…

  **Lexical shortlist for further review — NOT gold:**
  - AMOXICILLIN AND CLAVULANATE POTASSIUM (token overlap 2), `CHUNK:3db1b66f76b2c734e500`: 1 INDICATIONS AND USAGE Amoxicillin and clavulanate potassium tablets, amoxicillin and clavulanate potassium for oral suspension,…
  - LISINOPRIL (token overlap 2), `CHUNK:6915e887ba6b47cb9cd1`: levels were normal. In some cases, the angioedema was diagnosed by procedures including abdominal CT scan or ultrasound, or at…
  - WARFARIN SODIUM (token overlap 2), `CHUNK:62b5f89f5b15b6ce14e1`: Use in Specific Populations ( 8.1 )] . Warfarin sodium is contraindicated in patients with: Hemorrhagic tendencies or blood…
  - PANTOPRAZOLE SODIUM (token overlap 1), `CHUNK:91dfa087d52eec1489f9`: 6 ADVERSE REACTIONS Most common adverse reactions (>2%) are: headache, diarrhea, nausea, abdominal pain, vomiting, flatulence,…
  - RIVAROXABAN (token overlap 1), `CHUNK:373b8830d698dc120636`: for 24 hours. Should the physician decide to administer anticoagulation in the context of epidural or spinal anesthesia/analgesia…

## Q05 — semantic

Which official drug labels discuss a medicine prohibited in patients with a past allergic response to aspirin or other NSAIDs?

- Proposed source candidate(s): NAPROXEN SODIUM
- Source-based candidates: manual corpus review required.
- Notes: Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.

  - Evidence `CHUNK:5d5167e564156b2f6320`: 4 CONTRAINDICATIONS Naproxen sodium tablets are contraindicated in the following patients: Known hypersensitivity (e.g., anaphylactic reactions and serious skin reactions) to naproxen or any components of the drug product [ see Warnings and Precautions (5.7 , 5.9) ] History of asthma, urticaria, or other allergic-type reactions…

  **Lexical shortlist for further review — NOT gold:**
  - IBUPROFEN (token overlap 5), `CHUNK:2e81429d03d58ebd35eb`: 4 CONTRAINDICATIONS CALDOLOR is contraindicated in the following patients: Known hypersensitivity (e.g., anaphylactic reactions…
  - FLUOXETINE HYDROCHLORIDE (token overlap 5), `CHUNK:f8bc028d63a66b3f4713`: Allergic Reactions and Rash: Discontinue upon appearance of rash or allergic phenomena ( 5.3 ) Activation of Mania/Hypomania:…
  - NAPROXEN SODIUM (token overlap 5), `CHUNK:5d5167e564156b2f6320`: 4 CONTRAINDICATIONS Naproxen sodium tablets are contraindicated in the following patients: Known hypersensitivity (e.g.,…
  - PREDNISONE (token overlap 5), `CHUNK:1a67e03573aeb2e83b63`: may decrease the hepatic metabolism of certain corticosteroids, thereby increasing their effect. 7.13 Nonsteroidal…
  - LEVOTHYROXINE SODIUM (token overlap 4), `CHUNK:bd598b8c3657e06ff913`: or discontinuing levothyroxine sodium [see Drug Interactions (7.2) ] . 5.6 Decreased Bone Mineral Density Associated with Thyroid…

## Q06 — semantic

Which official drug labels discuss drug restriction involving monoamine oxidase inhibitors and a fourteen-day interval?

- Proposed source candidate(s): SERTRALINE HYDROCHLORIDE
- Source-based candidates: manual corpus review required.
- Notes: Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.; Shares a core fact/source with another query; avoid claiming all tests are independent.

  - Evidence `CHUNK:413bd1ff62ee459f93d0`: 4 CONTRAINDICATIONS Sertraline hydrochloride tablets are contraindicated in patients: • Taking, or within 14 days of stopping, MAOIs, (including the MAOIs linezolid and intravenous methylene blue) because of an increased risk of serotonin syndrome [ See Warnings and Precautions (5.2) , Drug Interactions (7.1) ] . • Taking…

  **Lexical shortlist for further review — NOT gold:**
  - FLUOXETINE HYDROCHLORIDE (token overlap 4), `CHUNK:80f1596472ef8ea7b846`: haloperidol and clozapine levels ( 7.7 ) Anticonvulsants: Potential for elevated phenytoin and carbamazepine levels and clinical…
  - BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE (token overlap 3), `CHUNK:6ece786c54fac4a8133e`: 4 CONTRAINDICATIONS Butalbital, Acetaminophen, Caffeine, and Codeine Phosphate Capsules are contraindicated for: All children…
  - METOPROLOL SUCCINATE (token overlap 3), `CHUNK:f16967f56c0d2a04c0f6`: 7 DRUG INTERACTIONS • Catecholamine-depleting drugs may have an additive effect when given with beta-blocking agents. ( 7.1 ) •…
  - SERTRALINE HYDROCHLORIDE (token overlap 3), `CHUNK:413bd1ff62ee459f93d0`: 4 CONTRAINDICATIONS Sertraline hydrochloride tablets are contraindicated in patients: • Taking, or within 14 days of stopping,…
  - BUTALBITAL, ASPIRIN, CAFFEINE AND CODEINE PHOSPHATE (token overlap 3), `CHUNK:e1281814846d79aa91f9`: 4 CONTRAINDICATIONS ASCOMP with Codeine is contraindicated for: All children younger than 12 years of age [see Warnings and…

## Q07 — semantic

Which official drug labels discuss interference with the antiplatelet effect of low-dose aspirin?

- Proposed source candidate(s): NAPROXEN SODIUM
- Source-based candidates: manual corpus review required.
- Notes: Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.

  - Evidence `CHUNK:e7c7e48f6bb9d190c82d`: serotonin reuptake inhibitors (SSRIs), and serotonin norepinephrine reuptake inhibitors (SNRIs) for signs of bleeding [ see Warnings and Precautions (5.12) ]. Aspirin Clinical Impact: A pharmacodynamic (PD) study has demonstrated an interaction in which lower dose naproxen (220mg/day or 220mg twice daily) interfered with the…

  **Lexical shortlist for further review — NOT gold:**
  - IBUPROFEN (token overlap 5), `CHUNK:c966267771e2038ac332`: reuptake inhibitors (SSRIs), and serotonin norepinephrine reuptake inhibitors (SNRIs) for signs of bleeding [ see Warnings and…
  - NAPROXEN SODIUM (token overlap 5), `CHUNK:e7c7e48f6bb9d190c82d`: serotonin reuptake inhibitors (SSRIs), and serotonin norepinephrine reuptake inhibitors (SNRIs) for signs of bleeding [ see…
  - CLOPIDOGREL BISULFATE (token overlap 3), `CHUNK:f696ac342fc028dc0dd7`: risk of bleeding due to an additive effect. Promptly evaluate any signs or symptoms of blood loss if patients are treated…
  - OMEPRAZOLE (token overlap 2), `CHUNK:fc937a27409957e28a81`: twice daily. See prescribing information for cilostazol. Phenytoin Clinical Impact: Potential for increased exposure of…
  - PANTOPRAZOLE SODIUM (token overlap 2), `CHUNK:a762ad42283a44a73efe`: and even death. Intervention: Monitor INR and prothrombin time. Dose adjustment of warfarin may be needed to maintain target INR…

## Q08 — semantic

Which official drug labels discuss an increase of INR potentially caused by enzyme inhibition?

- Proposed source candidate(s): WARFARIN SODIUM
- Source-based candidates: manual corpus review required.
- Notes: Semantic: full-corpus manual relevance judgment required; lexical shortlist is NOT exhaustive.

  - Evidence `CHUNK:7a3ddd18c8bf0d4ddc09`: to note that some drugs may interact by more than one mechanism. More frequent INR monitoring should be performed when starting or stopping other drugs, including botanicals, or when changing dosages of other drugs, including drugs intended for short-term use (e.g., antibiotics, antifungals, corticosteroids) [ see Boxed Warning…

  **Lexical shortlist for further review — NOT gold:**
  - TELMISARTAN AND AMLODIPINE (token overlap 3), `CHUNK:519e82b4f993955784a9`: possible inhibition of the metabolism of drugs metabolized by CYP2C19. 7.3 Drug Interactions with Amlodipine In clinical trials,…
  - VALSARTAN AND HYDROCHLOROTHIAZIDE (token overlap 3), `CHUNK:d0a4df7ebf7814129e3e`: of the diuretic is obtained. Carbamazepine: May lead to symptomatic hyponatremia. Ion exchange resins: Staggering the dosage of…
  - FLUOXETINE HYDROCHLORIDE (token overlap 3), `CHUNK:9a813d39a67cf8cb8f3b`: single doses of terfenadine (a CYP3A4 substrate), no increase in plasma terfenadine concentrations occurred with concomitant…
  - PREDNISONE (token overlap 3), `CHUNK:277f5b18d072baa166a7`: by cardiac enlargement and congestive heart failure [see Drug Interactions (7.14) ] . 7.3 Anticholinesterase Agents Concomitant…
  - CIPROFLOXACIN HYDROCHLORIDE (token overlap 3), `CHUNK:9ede29944934267fd764`: to the increase in INR (international normalized ratio) is difficult to assess. Monitor prothrombin time and INR frequently…

## Q09 — structural

Which drug labels in this collection contain AMLODIPINE BESYLATE as an active ingredient?

- Proposed source candidate(s): AMLODIPINE AND ATORVASTATIN; TELMISARTAN AND AMLODIPINE
- Source-based candidates (NOT approved gold): AMLODIPINE AND ATORVASTATIN; TELMISARTAN AND AMLODIPINE
- Notes: Source consistency check passed. Independent gold review still required.

  - Evidence `LABEL:c09c6dd4-0101-4551-878c-f28080948160#openfda.substance_name`: metadata pointer, not a text chunk
  - Evidence `LABEL:f0d9160e-9405-435e-9f36-75c537267221#openfda.substance_name`: metadata pointer, not a text chunk

## Q10 — structural

Which drug labels in this collection contain BUTALBITAL as an active ingredient?

- Proposed source candidate(s): BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE; BUTALBITAL, ASPIRIN, CAFFEINE AND CODEINE PHOSPHATE
- Source-based candidates (NOT approved gold): BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE; BUTALBITAL, ASPIRIN, CAFFEINE AND CODEINE PHOSPHATE
- Notes: Source consistency check passed. Independent gold review still required.

  - Evidence `LABEL:65596803-c8a0-47a5-b76a-e24e03cb5b85#openfda.substance_name`: metadata pointer, not a text chunk
  - Evidence `LABEL:ab86ae24-3103-4976-bd9d-8c90b76c5f29#openfda.substance_name`: metadata pointer, not a text chunk

## Q11 — structural

Which drug labels in this collection contain CAFFEINE as an active ingredient?

- Proposed source candidate(s): BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE; BUTALBITAL, ASPIRIN, CAFFEINE AND CODEINE PHOSPHATE
- Source-based candidates (NOT approved gold): BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE; BUTALBITAL, ASPIRIN, CAFFEINE AND CODEINE PHOSPHATE
- Notes: Source consistency check passed. Independent gold review still required.

  - Evidence `LABEL:65596803-c8a0-47a5-b76a-e24e03cb5b85#openfda.substance_name`: metadata pointer, not a text chunk
  - Evidence `LABEL:ab86ae24-3103-4976-bd9d-8c90b76c5f29#openfda.substance_name`: metadata pointer, not a text chunk

## Q12 — structural

Which drug labels in this collection contain CODEINE PHOSPHATE as an active ingredient?

- Proposed source candidate(s): BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE; BUTALBITAL, ASPIRIN, CAFFEINE AND CODEINE PHOSPHATE
- Source-based candidates (NOT approved gold): BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE; BUTALBITAL, ASPIRIN, CAFFEINE AND CODEINE PHOSPHATE
- Notes: Source consistency check passed. Independent gold review still required.

  - Evidence `LABEL:65596803-c8a0-47a5-b76a-e24e03cb5b85#openfda.substance_name`: metadata pointer, not a text chunk
  - Evidence `LABEL:ab86ae24-3103-4976-bd9d-8c90b76c5f29#openfda.substance_name`: metadata pointer, not a text chunk

## Q13 — structural

Which drug labels in this collection contain HYDROCHLOROTHIAZIDE as an active ingredient?

- Proposed source candidate(s): LOSARTAN POTASSIUM AND HYDROCHLOROTHIAZIDE; VALSARTAN AND HYDROCHLOROTHIAZIDE
- Source-based candidates (NOT approved gold): LOSARTAN POTASSIUM AND HYDROCHLOROTHIAZIDE; VALSARTAN AND HYDROCHLOROTHIAZIDE
- Notes: Source consistency check passed. Independent gold review still required.

  - Evidence `LABEL:4f06534c-c0d5-3f1f-e063-6394a90a8063#openfda.substance_name`: metadata pointer, not a text chunk
  - Evidence `LABEL:67e8d1ee-ea2c-48ad-911f-696692652d2e#openfda.substance_name`: metadata pointer, not a text chunk

## Q14 — structural

Which drug labels in this collection contain ACETAMINOPHEN as an active ingredient?

- Proposed source candidate(s): BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE
- Source-based candidates (NOT approved gold): BUTALBITAL, ACETAMINOPHEN, CAFFEINE AND CODEINE PHOSPHATE
- Notes: Source consistency check passed. Independent gold review still required.

  - Evidence `LABEL:ab86ae24-3103-4976-bd9d-8c90b76c5f29#openfda.substance_name`: metadata pointer, not a text chunk

## Q15 — structural

Which drug labels in this collection contain ALOGLIPTIN BENZOATE as an active ingredient?

- Proposed source candidate(s): ALOGLIPTIN AND METFORMIN HYDROCHLORIDE
- Source-based candidates (NOT approved gold): ALOGLIPTIN AND METFORMIN HYDROCHLORIDE
- Notes: Source consistency check passed. Independent gold review still required.

  - Evidence `LABEL:eb8e70d9-7ea0-4154-99b6-07e7ba15fe14#openfda.substance_name`: metadata pointer, not a text chunk

## Q16 — strict

Which drug labels explicitly list 'Coronary artery bypass graft (CABG) surgery setting' as a verified contraindication?

- Proposed source candidate(s): NAPROXEN SODIUM
- Source-based candidates (NOT approved gold): NAPROXEN SODIUM
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Shares a core fact/source with another query; avoid claiming all tests are independent.

  - Evidence `CHUNK:5d5167e564156b2f6320`: 4 CONTRAINDICATIONS Naproxen sodium tablets are contraindicated in the following patients: Known hypersensitivity (e.g., anaphylactic reactions and serious skin reactions) to naproxen or any components of the drug product [ see Warnings and Precautions (5.7 , 5.9) ] History of asthma, urticaria, or other allergic-type reactions…

## Q17 — strict

Which drug labels explicitly list 'Concomitant or recent (within 14 days) MAOI use, including linezolid and IV methylene blue' as a verified contraindication?

- Proposed source candidate(s): SERTRALINE HYDROCHLORIDE
- Source-based candidates (NOT approved gold): SERTRALINE HYDROCHLORIDE
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Shares a core fact/source with another query; avoid claiming all tests are independent.

  - Evidence `CHUNK:413bd1ff62ee459f93d0`: 4 CONTRAINDICATIONS Sertraline hydrochloride tablets are contraindicated in patients: • Taking, or within 14 days of stopping, MAOIs, (including the MAOIs linezolid and intravenous methylene blue) because of an increased risk of serotonin syndrome [ See Warnings and Precautions (5.2) , Drug Interactions (7.1) ] . • Taking…

## Q18 — strict

Which drug labels explicitly list 'Active ulceration or overt bleeding of gastrointestinal, genitourinary, or respiratory tract' as a verified contraindication?

- Proposed source candidate(s): WARFARIN SODIUM
- Source-based candidates (NOT approved gold): WARFARIN SODIUM
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.

  - Evidence `CHUNK:62b5f89f5b15b6ce14e1`: Use in Specific Populations ( 8.1 )] . Warfarin sodium is contraindicated in patients with: Hemorrhagic tendencies or blood dyscrasias Recent or contemplated surgery of the central nervous system or eye, or traumatic surgery resulting in large open surfaces [see Warnings and Precautions ( 5.8 )] Bleeding tendencies associated…

## Q19 — strict

Which drug labels explicitly list 'History of asthma, urticaria, or allergic-type reactions after aspirin or other NSAIDs' as a verified contraindication?

- Proposed source candidate(s): NAPROXEN SODIUM
- Source-based candidates (NOT approved gold): NAPROXEN SODIUM
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.

  - Evidence `CHUNK:5d5167e564156b2f6320`: 4 CONTRAINDICATIONS Naproxen sodium tablets are contraindicated in the following patients: Known hypersensitivity (e.g., anaphylactic reactions and serious skin reactions) to naproxen or any components of the drug product [ see Warnings and Precautions (5.7 , 5.9) ] History of asthma, urticaria, or other allergic-type reactions…

## Q20 — strict

Which drug labels explicitly list 'Concomitant pimozide use' as a verified contraindication?

- Proposed source candidate(s): SERTRALINE HYDROCHLORIDE
- Source-based candidates (NOT approved gold): SERTRALINE HYDROCHLORIDE
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Shares a core fact/source with another query; avoid claiming all tests are independent.

  - Evidence `CHUNK:413bd1ff62ee459f93d0`: 4 CONTRAINDICATIONS Sertraline hydrochloride tablets are contraindicated in patients: • Taking, or within 14 days of stopping, MAOIs, (including the MAOIs linezolid and intravenous methylene blue) because of an increased risk of serotonin syndrome [ See Warnings and Precautions (5.2) , Drug Interactions (7.1) ] . • Taking…

## Q21 — strict

Which drug labels explicitly list 'Bacterial endocarditis' as a verified contraindication?

- Proposed source candidate(s): WARFARIN SODIUM
- Source-based candidates (NOT approved gold): WARFARIN SODIUM
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Shares a core fact/source with another query; avoid claiming all tests are independent.

  - Evidence `CHUNK:62b5f89f5b15b6ce14e1`: Use in Specific Populations ( 8.1 )] . Warfarin sodium is contraindicated in patients with: Hemorrhagic tendencies or blood dyscrasias Recent or contemplated surgery of the central nervous system or eye, or traumatic surgery resulting in large open surfaces [see Warnings and Precautions ( 5.8 )] Bleeding tendencies associated…

## Q22 — strict

Which drug labels explicitly list 'Hypersensitivity to naproxen or any product components' as a verified contraindication?

- Proposed source candidate(s): NAPROXEN SODIUM
- Source-based candidates (NOT approved gold): NAPROXEN SODIUM
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.

  - Evidence `CHUNK:5d5167e564156b2f6320`: 4 CONTRAINDICATIONS Naproxen sodium tablets are contraindicated in the following patients: Known hypersensitivity (e.g., anaphylactic reactions and serious skin reactions) to naproxen or any components of the drug product [ see Warnings and Precautions (5.7 , 5.9) ] History of asthma, urticaria, or other allergic-type reactions…

## Q23 — strict

Which drug labels explicitly list 'Known hypersensitivity to sertraline or excipients' as a verified contraindication?

- Proposed source candidate(s): SERTRALINE HYDROCHLORIDE
- Source-based candidates (NOT approved gold): SERTRALINE HYDROCHLORIDE
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.

  - Evidence `CHUNK:413bd1ff62ee459f93d0`: 4 CONTRAINDICATIONS Sertraline hydrochloride tablets are contraindicated in patients: • Taking, or within 14 days of stopping, MAOIs, (including the MAOIs linezolid and intravenous methylene blue) because of an increased risk of serotonin syndrome [ See Warnings and Precautions (5.2) , Drug Interactions (7.1) ] . • Taking…

## Q24 — strict

Which drug labels explicitly prohibit coadministration with monoamine oxidase inhibitors?

- Proposed source candidate(s): SERTRALINE HYDROCHLORIDE
- Source-based candidates (NOT approved gold): SERTRALINE HYDROCHLORIDE
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.

  - Evidence `CHUNK:83516e488c1055ccfb25`: 7 DRUG INTERACTIONS • Protein-bound drugs: Monitor for adverse reactions and reduce dosage of sertraline hydrochloride or other protein-bound drugs (e.g., warfarin) as warranted. ( 7.1 , 12.3 ) • CYP2D6 substrates: Reduce dosage of drugs metabolized by CYP2D6. ( 7.1 , 12.3 ) 7.1 Clinically Significant Drug Interactions Table 5…

## Q25 — strict

Which drug labels have a documented interaction with warfarin that requires monitoring but is NOT classified as contraindicated coadministration in the reviewed records?

- Proposed source candidate(s): NAPROXEN SODIUM; SERTRALINE HYDROCHLORIDE
- Source-based candidates (NOT approved gold): NAPROXEN SODIUM; SERTRALINE HYDROCHLORIDE
- Notes: Closed-world negative condition applies ONLY to reviewed interactions; not a clinical absence claim.; Requires caution: NOT a verified contraindication in the 9 reviewed interaction records only.

  - Evidence `CHUNK:3ea37fec93dba833a4e9`: 7 DRUG INTERACTIONS See Table 1 for clinically significant drug interactions with naproxen. Table 1: Clinically Significant Drug Interactions with naproxen Drugs That Interfere with Hemostasis Clinical Impact: Naproxen and anticoagulants such as warfarin have a synergistic effect on bleeding. The concomitant use of naproxen and…
  - Evidence `CHUNK:b9546046d5d842a51d7c`: lithium, tryptophan, buspirone, amphetamines, and St. John’s Wort. Drugs that Interfere with Hemostasis (antiplatelet agents and anticoagulants) Clinical Impact: The concurrent use of an antiplatelet agent or anticoagulant with sertraline hydrochloride may potentiate the risk of bleeding. Intervention: Inform patients of the…

## Q26 — multi_hop

Which drug labels contain NAPROXEN SODIUM AND explicitly list 'History of asthma, urticaria, or allergic-type reactions after aspirin or other NSAIDs' as a contraindication?

- Proposed source candidate(s): NAPROXEN SODIUM
- Source-based candidates (NOT approved gold): NAPROXEN SODIUM
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Primary ingredient is explicitly named, so this is a controlled conjunctive traversal test.

  - Evidence `CHUNK:5d5167e564156b2f6320`: 4 CONTRAINDICATIONS Naproxen sodium tablets are contraindicated in the following patients: Known hypersensitivity (e.g., anaphylactic reactions and serious skin reactions) to naproxen or any components of the drug product [ see Warnings and Precautions (5.7 , 5.9) ] History of asthma, urticaria, or other allergic-type reactions…

## Q27 — multi_hop

Which drug labels contain SERTRALINE HYDROCHLORIDE AND explicitly list 'Known hypersensitivity to sertraline or excipients' as a contraindication?

- Proposed source candidate(s): SERTRALINE HYDROCHLORIDE
- Source-based candidates (NOT approved gold): SERTRALINE HYDROCHLORIDE
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Primary ingredient is explicitly named, so this is a controlled conjunctive traversal test.

  - Evidence `CHUNK:413bd1ff62ee459f93d0`: 4 CONTRAINDICATIONS Sertraline hydrochloride tablets are contraindicated in patients: • Taking, or within 14 days of stopping, MAOIs, (including the MAOIs linezolid and intravenous methylene blue) because of an increased risk of serotonin syndrome [ See Warnings and Precautions (5.2) , Drug Interactions (7.1) ] . • Taking…

## Q28 — multi_hop

Which drug labels contain WARFARIN SODIUM AND explicitly list 'Active ulceration or overt bleeding of gastrointestinal, genitourinary, or respiratory tract' as a contraindication?

- Proposed source candidate(s): WARFARIN SODIUM
- Source-based candidates (NOT approved gold): WARFARIN SODIUM
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Primary ingredient is explicitly named, so this is a controlled conjunctive traversal test.

  - Evidence `CHUNK:62b5f89f5b15b6ce14e1`: Use in Specific Populations ( 8.1 )] . Warfarin sodium is contraindicated in patients with: Hemorrhagic tendencies or blood dyscrasias Recent or contemplated surgery of the central nervous system or eye, or traumatic surgery resulting in large open surfaces [see Warnings and Precautions ( 5.8 )] Bleeding tendencies associated…

## Q29 — multi_hop

Which drug labels contain NAPROXEN SODIUM AND have a verified interaction with Warfarin sodium?

- Proposed source candidate(s): NAPROXEN SODIUM
- Source-based candidates (NOT approved gold): NAPROXEN SODIUM
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Primary ingredient is explicitly named, so this is a controlled conjunctive traversal test.

  - Evidence `CHUNK:3ea37fec93dba833a4e9`: 7 DRUG INTERACTIONS See Table 1 for clinically significant drug interactions with naproxen. Table 1: Clinically Significant Drug Interactions with naproxen Drugs That Interfere with Hemostasis Clinical Impact: Naproxen and anticoagulants such as warfarin have a synergistic effect on bleeding. The concomitant use of naproxen and…

## Q30 — multi_hop

Which drug labels contain SERTRALINE HYDROCHLORIDE AND have a verified interaction with Warfarin sodium?

- Proposed source candidate(s): SERTRALINE HYDROCHLORIDE
- Source-based candidates (NOT approved gold): SERTRALINE HYDROCHLORIDE
- Notes: Only currently reviewed facts are covered; benchmark wording must stay within this scope.; Primary ingredient is explicitly named, so this is a controlled conjunctive traversal test.

  - Evidence `CHUNK:b9546046d5d842a51d7c`: lithium, tryptophan, buspirone, amphetamines, and St. John’s Wort. Drugs that Interfere with Hemostasis (antiplatelet agents and anticoagulants) Clinical Impact: The concurrent use of an antiplatelet agent or anticoagulant with sertraline hydrochloride may potentiate the risk of bleeding. Intervention: Inform patients of the…
