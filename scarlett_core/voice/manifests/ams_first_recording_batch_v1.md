---
title: AMS First Recording Batch v1
category: Voice Manifest
status: approved_script
req: REQ-157
language: fr-CA
line_count: 28
---

# AMS First Recording Batch v1

First approved short reusable Scarlett recording batch. Record these as first-audio/opening lines only; deterministic answer bodies remain generated.

## Global direction

- Calm, deliberate, premium, kind, competent.
- `0.75` speed target for quick bridges/receipts unless a later voice pass says otherwise.
- Consistent `vous` phrasing.
- No fake transfer, fake booking, fake callback, fake link-send, or fake submission.

## Greeting Orientation

01. `ams-int-001` / `greeting` / `ams/ams-int-001-greeting.wav`
   - Bonjour, je suis Scarlett.
   - Note: warm, concise, receptionist calm; no sales brightness

02. `ams-int-002` / `greeting_allo` / `ams/ams-int-002-greeting_allo.wav`
   - Allô, je suis Scarlett.
   - Note: warm, concise, receptionist calm; no sales brightness

03. `ams-int-004` / `how_are_you` / `ams/ams-int-004-how_are_you.wav`
   - Ça va très bien, merci. Quelle information AMS souhaitez-vous vérifier?
   - Note: warm, concise, receptionist calm; no sales brightness

04. `ams-int-050` / `what_can_help` / `ams/ams-int-050-what_can_help.wav`
   - Je peux vous aider avec les formations, les prix, les campus, l’inscription et le bon parcours.
   - Note: warm, concise, receptionist calm; no sales brightness

## Repair Recovery

05. `ams-int-036` / `repeat` / `ams/ams-int-036-repeat.wav`
   - D’accord. Je vous le redis simplement.
   - Note: gentle, short, interruptible; make friction feel normal

06. `ams-int-037` / `unclear` / `ams/ams-int-037-unclear.wav`
   - C’est le prix, le choix du programme, le campus, ou l’inscription qui n’est pas clair?
   - Note: gentle, short, interruptible; make friction feel normal

07. `ams-int-038` / `didnt_hear` / `ams/ams-int-038-didnt_hear.wav`
   - Pas de problème — je le reformule plus simplement.
   - Note: gentle, short, interruptible; make friction feel normal

08. `ams-int-039` / `stt_failure` / `ams/ams-int-039-stt_failure.wav`
   - Désolée, je n’ai pas bien entendu. Pouvez-vous répéter?
   - Note: gentle, short, interruptible; make friction feel normal

## Signup Action Safety

09. `ams-int-023` / `signup_direct` / `ams/ams-int-023-signup_direct.wav`
   - C’est pour le Niveau 1, un autre niveau, ou un cours à la carte?
   - Note: helpful but careful; never imply submission or booking

10. `ams-int-024` / `signup_link` / `ams/ams-int-024-signup_link.wav`
   - Oui — je peux vous guider vers le bon lien d’inscription officiel, sans rien soumettre à votre place.
   - Note: helpful but careful; never imply submission or booking

11. `ams-int-025` / `reserve_place` / `ams/ams-int-025-reserve_place.wav`
   - Oui — je peux vous guider, mais la place doit être confirmée par l’AMS.
   - Note: helpful but careful; never imply submission or booking

## Handoff Human

12. `ams-int-047` / `julie` / `ams/ams-int-047-julie.wav`
   - Oui — je peux vous orienter vers le bon contact pour joindre Julie, sans prétendre la transférer directement.
   - Note: steady and honest; never sound like a live transfer is happening

13. `ams-int-048` / `human` / `ams/ams-int-048-human.wav`
   - Bien sûr — je peux vous orienter vers une personne de l’AMS sans prétendre transférer l’appel moi-même.
   - Note: steady and honest; never sound like a live transfer is happening

## Price Financing

14. `ams-int-011` / `price_n1` / `ams/ams-int-011-price_n1.wav`
   - Le Niveau 1 est à 4 995 $, ou à partir de 104 $ par semaine.
   - Note: clear and settled; numbers crisp, no upsell energy

15. `ams-int-012` / `price_n2` / `ams/ams-int-012-price_n2.wav`
   - Le Niveau 2 est à 7 345 $, ou à partir de 111 $ par semaine.
   - Note: clear and settled; numbers crisp, no upsell energy

16. `ams-int-013` / `price_n3` / `ams/ams-int-013-price_n3.wav`
   - Le Niveau 3 est à 3 595 $, ou à partir de 97 $ par semaine.
   - Note: clear and settled; numbers crisp, no upsell energy

17. `ams-int-014` / `total_n1_n2` / `ams/ams-int-014-total_n1_n2.wav`
   - Niveau 1 plus Niveau 2, le total est 12 340 $.
   - Note: clear and settled; numbers crisp, no upsell energy

18. `ams-int-015` / `total_all` / `ams/ams-int-015-total_all.wav`
   - Les trois niveaux ensemble totalisent 15 935 $.
   - Note: clear and settled; numbers crisp, no upsell energy

19. `ams-int-016` / `financing` / `ams/ams-int-016-financing.wav`
   - Oui, il y a des options de paiement et du financement peut être disponible.
   - Note: clear and settled; numbers crisp, no upsell energy

20. `ams-int-017` / `weekly` / `ams/ams-int-017-weekly.wav`
   - Oui — ça dépend du niveau, je vous donne les repères.
   - Note: clear and settled; numbers crisp, no upsell energy

21. `ams-int-018` / `too_expensive` / `ams/ams-int-018-too_expensive.wav`
   - Je comprends — je peux vous montrer les options de paiement sans vous pousser.
   - Note: clear and settled; numbers crisp, no upsell energy

## Continuing Ed Browsing

22. `ams-int-027` / `continuing_ed_list` / `ams/ams-int-027-continuing_ed_list.wav`
   - Oui, bien sûr. Je vous regroupe les options à la carte par thème pour que ce soit plus facile à comparer.
   - Note: helpful browsing opener; body remains generated from facts

23. `ams-int-028` / `specific_course` / `ams/ams-int-028-specific_course.wav`
   - Oui — je vous donne le repère précis pour ce cours.
   - Note: helpful browsing opener; body remains generated from facts

24. `ams-int-029` / `sport_course` / `ams/ams-int-029-sport_course.wav`
   - Oui — pour le sport, je regarde surtout récupération, mobilité et douleurs musculaires.
   - Note: helpful browsing opener; body remains generated from facts

25. `ams-int-030` / `aroma_course` / `ams/ams-int-030-aroma_course.wav`
   - Oui — l’AMS offre l’aromathérapie comme formation à la carte.
   - Note: helpful browsing opener; body remains generated from facts

## Campus Location

26. `ams-int-019` / `campus_list` / `ams/ams-int-019-campus_list.wav`
   - L’école a huit campus au Québec.
   - Note: orientation opener only; addresses/distances remain generated

27. `ams-int-020` / `nearest_campus` / `ams/ams-int-020-nearest_campus.wav`
   - Je peux vous situer le campus probablement le plus proche, avec une estimation locale.
   - Note: orientation opener only; addresses/distances remain generated

28. `ams-int-021` / `campus_address` / `ams/ams-int-021-campus_address.wav`
   - Oui — je vous donne l’adresse du campus demandé.
   - Note: orientation opener only; addresses/distances remain generated
