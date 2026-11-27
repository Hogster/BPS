// BPS panel translations. English is the source language; every other
// language is a dictionary from the English text to the translation.
//
// The language follows the Home Assistant user's language (the panel element
// passes hass.language in with the access token); unknown languages fall back
// to English. Translation happens on the DOM: text nodes and the title /
// placeholder / aria-label attributes are looked up as they appear, so the
// app code mostly stays in English. Keys with {} are patterns: "{}" matches
// any text and is carried over in order. Elements with data-i18n="key" get
// their innerHTML from HTML[lang][key] (for paragraphs with inline markup).
//
// To add a language: add a dictionary under TEXT and HTML with the same keys.
(function () {
    "use strict";

    const TEXT = { sv: {
        // ---- tabs, sidebar, common ----
        "Map & Setup": "Karta & inställning",
        "Receiver Calibration": "Mottagarkalibrering",
        "Debugging": "Felsökning",
        "Settings": "Inställningar",
        "Learned": "Lärt sig",
        "Toggle light / dark theme": "Växla ljust / mörkt tema",
        "Toggle theme": "Växla tema",
        "Switch to dark theme": "Byt till mörkt tema",
        "Switch to light theme": "Byt till ljust tema",
        "Switch to {}": "Byt till {}",
        "Floor": "Våning",
        "Floor name": "Våningsnamn",
        "e.g. Ground floor": "t.ex. Bottenvåning",
        "Floor plan image": "Planritning",
        "Upload": "Ladda upp",
        "Tools": "Verktyg",
        "View": "Visa",
        "Tracking": "Spårning",
        "Entities to track:": "Enheter att spåra:",
        "Add device to track": "Lägg till enhet att spåra",
        "Start tracking": "Starta spårning",
        "Stop tracking": "Stoppa spårning",
        "Stop tracking this device": "Sluta spåra den här enheten",
        "Trace path": "Rita spår",
        "Draw Zone": "Rita zon",
        "Draw Sub-Zone": "Rita delzon",
        "Place Receiver": "Placera mottagare",
        "Set Scale": "Ange skala",
        "Scale set": "Skala angiven",
        "Scale not set": "Skala saknas",
        "Save Floor Plan": "Spara planritning",
        "Delete Floor": "Ta bort våning",
        "Delete floor": "Ta bort våning",
        "Clear Canvas": "Rensa ritytan",
        "Adjust zones": "Justera zoner",
        "Adjust Zones": "Justera zoner",
        "Adjust Sub-zones": "Justera delzoner",
        "Square rooms": "Räta rum",
        "Move": "Flytta",
        "Grid: off": "Rutnät: av",
        "Colours: on": "Färger: på",
        "⤢ Reset view": "⤢ Återställ vy",
        "Reset zoom and position": "Återställ zoom och läge",
        "✓ Save": "✓ Spara",
        "✕ Cancel": "✕ Avbryt",
        "Cancel": "Avbryt",
        "Save current tool": "Spara aktuellt verktyg",
        "Cancel current tool (Esc)": "Avbryt aktuellt verktyg (Esc)",
        "Cancel (discard this zone / sub-zone)": "Avbryt (släng zonen / delzonen)",
        "Cancel receiver placement": "Avbryt placering av mottagare",
        "Zones & Receivers": "Zoner & mottagare",
        "Select a floor to see its zones and receivers.": "Välj en våning för att se dess zoner och mottagare.",
        "Enable “Move receivers”, drag one on the map, then Save Floor Plan.": "Slå på ”Flytta mottagare”, dra en på kartan och spara sedan planritningen.",
        "Search receivers…": "Sök mottagare…",
        "-- Select receiver --": "-- Välj mottagare --",
        "-- Please choose an option --": "-- Välj ett alternativ --",
        "--Please choose an option--": "--Välj ett alternativ--",
        "Custom name…": "Eget namn…",
        "Custom name": "Eget namn",
        "Select existing": "Välj befintlig",
        "Known receivers:": "Kända mottagare:",
        "Suggested receivers": "Föreslagna mottagare",
        "Tracker icon": "Spårningsikon",
        "Upload icon": "Ladda upp ikon",
        "Beacon": "Beacon",
        "Current zone:": "Aktuell zon:",
        "Copy": "Kopiera",
        "show all": "visa alla",
        "show all again": "visa alla igen",
        "Mount height m (optional)": "Monteringshöjd m (valfritt)",
        "Height?": "Höjd?",
        "Mount height above this floor (m). Click to change.": "Monteringshöjd över golvet (m). Klicka för att ändra.",
        "Height above this floor the receiver is mounted at, in metres": "Höjd över golvet där mottagaren sitter, i meter",
        "Mount height of \"{}\" above this floor, in metres (empty = unknown).": "Monteringshöjd för ”{}” över golvet, i meter (tomt = okänd).",
        "Mount height must be a number between 0 and 10 metres.": "Monteringshöjden måste vara ett tal mellan 0 och 10 meter.",
        "Height of \"{}\" set to {} m — Save Floor Plan to keep it, then recalibrate.": "Höjden för ”{}” är satt till {} m – spara planritningen och kalibrera sedan om.",
        "Height of \"{}\" cleared — Save Floor Plan to keep it, then recalibrate.": "Höjden för ”{}” är borttagen – spara planritningen och kalibrera sedan om.",
        "Zone names": "Zonnamn",
        "Distances": "Avstånd",
        "Receiver distances": "Mottagaravstånd",
        "Click to isolate this device on the map (click again to show all)": "Klicka för att visa bara den här enheten på kartan (klicka igen för att visa alla)",

        // ---- map: help texts and messages ----
        "Click the floor image to place the zone's corners, one by one — any shape with three or more corners works. Drag a corner to adjust it, or drag the inside of the zone to move the whole zone. Right-click a corner to delete it. Enter the zone name (matching your Home Assistant areas is a good idea), then press ✓ Save. Press Esc or ✕ Cancel to back out.":
            "Klicka på planritningen för att placera zonens hörn, ett i taget – alla former med tre eller fler hörn fungerar. Dra i ett hörn för att justera det, eller dra inuti zonen för att flytta hela zonen. Högerklicka på ett hörn för att ta bort det. Skriv zonens namn (gärna samma som rummen i Home Assistant) och tryck på ✓ Spara. Tryck Esc eller ✕ Avbryt för att backa.",
        "Click inside the zone you want to add a sub-zone to — that becomes its parent — then keep clicking to place corners (they stay inside the parent). Drag a corner to adjust it, drag the inside to move it, right-click a corner to delete it. Name it (e.g. Couch), then press ✓ Save. Press Esc or ✕ Cancel to back out.":
            "Klicka inuti zonen som delzonen ska ligga i – den blir dess förälder – och fortsätt klicka för att placera hörn (de stannar inuti föräldern). Dra i ett hörn för att justera det, dra inuti för att flytta, högerklicka på ett hörn för att ta bort det. Ge den ett namn (t.ex. Soffa) och tryck på ✓ Spara. Tryck Esc eller ✕ Avbryt för att backa.",
        "Click inside the zone you want to add a sub-zone to.": "Klicka inuti zonen som delzonen ska ligga i.",
        "Click inside a zone first to choose the sub-zone's parent.": "Klicka först inuti en zon för att välja delzonens förälder.",
        "Drag a corner to move it, drag the inside to move the whole zone, right-click a corner to delete it, or click empty space to add one. Press ✓ Save to keep the changes.":
            "Dra i ett hörn för att flytta det, dra inuti för att flytta hela zonen, högerklicka på ett hörn för att ta bort det eller klicka på en tom yta för att lägga till ett. Tryck på ✓ Spara för att behålla ändringarna.",
        "Corners stay inside the parent zone. Drag a corner, drag the inside to move it, right-click a corner to delete it. Press ✓ Save to keep the changes.":
            "Hörnen stannar inuti föräldrazonen. Dra i ett hörn, dra inuti för att flytta, högerklicka på ett hörn för att ta bort det. Tryck på ✓ Spara för att behålla ändringarna.",
        "Place a BLE receiver by clicking its location on the floorplan, then pick it from the list. The list shows every receiver Bermuda currently reports (the part after \"_distance_to_\" in its sensors); receivers already placed on any floor are hidden, since a receiver belongs to one floor. Pick \"Custom name…\" to type a name manually, then press ✓ Save. Press Esc or ✕ Cancel to back out.":
            "Placera en BLE-mottagare genom att klicka där den sitter på planritningen och välj den sedan i listan. Listan visar alla mottagare som Bermuda rapporterar just nu (delen efter ”_distance_to_” i sensorerna); mottagare som redan är placerade på någon våning döljs, eftersom en mottagare hör till en våning. Välj ”Eget namn…” för att skriva ett namn själv och tryck på ✓ Spara. Tryck Esc eller ✕ Avbryt för att backa.",
        "Set the scale by clicking on the desired starting point and then again on the desired end point. Enter the actual (real-world) distance in the input element, then press ✓ Save. Press Esc or ✕ Cancel to back out.":
            "Ange skalan genom att klicka på en startpunkt och sedan på en slutpunkt. Skriv in det verkliga avståndet i fältet och tryck på ✓ Spara. Tryck Esc eller ✕ Avbryt för att backa.",
        "Draw the path each tracked device has taken since tracking started, in that device's colour — brighter is more recent. The traces clear when a new tracking session starts.":
            "Ritar vägen varje spårad enhet har tagit sedan spårningen startade, i enhetens färg – ljusare är nyare. Spåren rensas när en ny spårning startar.",
        "Show each receiver's measured distance to the tracked beacons, with the value on top of each receiver. With one beacon shown, each receiver draws a full distance circle (its own colour) with a thick line to the beacon inside it — where the circles intersect is the beacon. With several beacons the circles would overlap into noise, so each beacon instead shows thin lines to the receivers hearing it, in that beacon's colour. Click a beacon (on the map or in the list above) to isolate it.":
            "Visar varje mottagares uppmätta avstånd till de spårade enheterna, med värdet ovanpå mottagaren. Med en enhet visad ritar varje mottagare en avståndscirkel (i sin egen färg) med en tjock linje till enheten – där cirklarna korsar varandra är enheten. Med flera enheter blir cirklarna bara brus, så då visar varje enhet tunna linjer till mottagarna som hör den, i enhetens färg. Klicka på en enhet (på kartan eller i listan ovan) för att visa bara den.",
        "When on, drag receivers on the map to move them. When off, dragging pans the map and clicking a receiver focuses it (only that receiver and its circle stay visible).":
            "När det är på drar du mottagare på kartan för att flytta dem. När det är av panorerar du kartan genom att dra, och ett klick på en mottagare fokuserar den (bara den och dess cirkel syns).",
        "Editing zone": "Redigerar zon",
        "Editing sub-zone": "Redigerar delzon",
        "this zone": "den här zonen",
        "this sub-zone": "den här delzonen",
        "Please provide a name.": "Ange ett namn.",
        "Please enter a floor name!": "Ange ett våningsnamn!",
        "Floor name must be set.": "Våningsnamn måste anges.",
        "Floor '{}' already exists.": "Våningen ”{}” finns redan.",
        "Floor with name '{}' not found.": "Hittade ingen våning med namnet ”{}”.",
        "Added new floor: {}": "Ny våning tillagd: {}",
        "The floor named {} has been removed!": "Våningen {} är borttagen!",
        "Remove the floor \"{}\"? This deletes its map, zones and sub-zones.": "Ta bort våningen ”{}”? Dess karta, zoner och delzoner tas bort.",
        "Please load a floorplan first.": "Ladda en planritning först.",
        "Please draw a line first.": "Rita en linje först.",
        "Please enter the actual length in meters.": "Ange den verkliga längden i meter.",
        "You have not added a scale, it won't work without it!": "Du har inte angett någon skala – det fungerar inte utan den!",
        "No line drawn": "Ingen linje ritad",
        "Line length: {}": "Linjens längd: {}",
        "Select a floor first.": "Välj en våning först.",
        "No floor image is selected — please choose the floor image again.": "Ingen planritning är vald – välj bilden igen.",
        "Could not load the floor image for this map. Re-select it or upload a new image.": "Kunde inte läsa in planritningen för den här kartan. Välj den igen eller ladda upp en ny bild.",
        "Failed to load floor image: {}": "Kunde inte läsa in planritningen: {}",
        "No file uploaded.": "Ingen fil uppladdad.",
        "Choose an icon file first.": "Välj en ikonfil först.",
        "Could not upload icon.": "Kunde inte ladda upp ikonen.",
        "Tracker icon uploaded. Click Save Floor Plan to persist.": "Ikonen är uppladdad. Spara planritningen för att behålla den.",
        "Add at least one device to track!": "Lägg till minst en enhet att spåra!",
        "Add a device to track first.": "Lägg till en enhet att spåra först.",
        "Receiver coordinates must be set — click the floorplan first.": "Mottagarens läge saknas – klicka på planritningen först.",
        "Select a receiver from the list (or pick Custom name… and type one).": "Välj en mottagare i listan (eller välj Eget namn… och skriv ett).",
        "A zone needs at least three corners.": "En zon behöver minst tre hörn.",
        "A sub-zone needs at least three corners.": "En delzon behöver minst tre hörn.",
        "A zone or sub-zone can have at most {} corners.": "En zon eller delzon kan ha högst {} hörn.",
        "Draw at least one zone first — a sub-zone is placed inside a zone.": "Rita minst en zon först – en delzon placeras inuti en zon.",
        "Draw at least two zones on this floor first.": "Rita minst två zoner på den här våningen först.",
        "Draw at least one sub-zone on this floor first.": "Rita minst en delzon på den här våningen först.",
        "Zone saved: {}": "Zonen är sparad: {}",
        "Sub-zone saved: {}": "Delzonen är sparad: {}",
        "'{}' with the name '{}' already exists on {}.": "{} med namnet ”{}” finns redan på {}.",
        "Remove zone \"{}\"?": "Ta bort zonen ”{}”?",
        "Remove zone \"{}\" and its {} sub-zone(s)?": "Ta bort zonen ”{}” och dess {} delzon(er)?",
        "Remove sub-zone \"{}\"?": "Ta bort delzonen ”{}”?",
        "Remove receiver \"{}\"?": "Ta bort mottagaren ”{}”?",
        "Removed zone \"{}\"": "Zonen ”{}” är borttagen",
        "Removed sub-zone \"{}\"": "Delzonen ”{}” är borttagen",
        "Removed receiver \"{}\"": "Mottagaren ”{}” är borttagen",
        "\"{}\" marked no-go — Save Floor Plan to keep it.": "”{}” är markerad som spärrad yta – spara planritningen för att behålla det.",
        "\"{}\" is no longer no-go — Save Floor Plan to keep it.": "”{}” är inte längre spärrad – spara planritningen för att behålla det.",
        "Zone colour updated — Save Floor Plan to keep it.": "Zonfärgen är ändrad – spara planritningen för att behålla den.",
        "Links for \"{}\" updated — Save Floor Plan to keep them.": "Kopplingarna för ”{}” är ändrade – spara planritningen för att behålla dem.",
        "Re-linked \"{}\" → \"{}\". Save Floor Plan to keep it.": "Kopplade om ”{}” → ”{}”. Spara planritningen för att behålla det.",
        "{} adjusted — review, then Save Floor Plan (reload to discard).": "{} justerade – granska och spara sedan planritningen (ladda om för att slänga).",
        "clamped to parents": "anpassade till föräldern",
        "overlaps removed": "överlapp borttagna",
        "Adjust failed.": "Justeringen misslyckades.",
        "Unlinked sub-zones": "Delzoner utan förälder",
        "Saved successfully!": "Sparat!",
        "Error saving data!": "Fel när data skulle sparas!",
        "Error saving data:": "Fel när data skulle sparas:",
        "Could not load maps.": "Kunde inte läsa in kartorna.",
        "Could not load Home Assistant devices.": "Kunde inte läsa in enheter från Home Assistant.",
        "(max {}cm)": "(max {} cm)",

        // ---- zone links dialog ----
        "Link devices — {}": "Koppla enheter – {}",
        "Pick what belongs to this zone. Suggestions come from the HA area and from names; nothing is linked until you tick it.":
            "Välj vad som hör till zonen. Förslagen kommer från rummet i HA och från namn; inget kopplas förrän du kryssar i det.",
        "Home Assistant area": "Rum i Home Assistant",
        "Media players": "Mediaspelare",
        "Speakers / TVs in this zone": "Högtalare / tv i den här zonen",
        "Presence sensors": "Närvarosensorer",
        "Cameras (person count), mmWave, occupancy": "Kameror (antal personer), mmWave, närvaro",
        "+ Add other…": "+ Lägg till annan…",
        "same area": "samma rum",
        "Nothing linked or suggested.": "Inget kopplat eller föreslaget.",

        // ---- calibration ----
        "Compares the distances receivers measure between each other (each probe advertises an iBeacon) with their placed positions, and fits a per-receiver distance correction. Select the floor first, then sample while the house is quiet.":
            "Jämför avstånden som mottagarna mäter till varandra (varje mottagare sänder en iBeacon) med deras placering på kartan och räknar fram en avståndskorrigering per mottagare. Välj våning först och samla sedan data när det är lugnt i huset.",
        "Auto calibration": "Automatisk kalibrering",
        "Continuously samples in the background, re-solves every 15 minutes for every floor, and re-applies corrections whenever they change. Survives Home Assistant restarts.":
            "Samlar data i bakgrunden, räknar om var 15:e minut för varje våning och tillämpar korrigeringarna när de ändras. Fortsätter efter omstart av Home Assistant.",
        "Sample 5 minutes": "Samla 5 minuter",
        "Sample 10 minutes": "Samla 10 minuter",
        "Sample 30 minutes": "Samla 30 minuter",
        "Start calibration": "Starta kalibrering",
        "Apply corrections": "Tillämpa korrigeringar",
        "Reset corrections": "Återställ korrigeringar",
        "Calibration status:": "Kalibreringsstatus:",
        "Idle. Select a floor, then start a run — or enable auto calibration.": "Vilar. Välj en våning och starta en körning – eller slå på automatisk kalibrering.",
        "Auto calibration running · {} receiver pairs in the window": "Automatisk kalibrering pågår · {} mottagarpar i fönstret",
        "Sampling floor {}… {}:{}": "Samlar data för våning {}… {}:{}",
        "of {} min · {} receiver pairs heard so far.": "av {} min · {} mottagarpar hörda hittills.",
        "· first solve after a few minutes of data": "· första beräkningen efter några minuters data",
        "· last solve {}": "· senaste beräkning {}",
        "· floor {}: {} pairs used,": "· våning {}: {} par använda,",
        "typical error ×{} → ×{} predicted after correction.": "typiskt fel ×{} → ×{} förväntat efter korrigering.",
        "typical error ×{} → ×{}": "typiskt fel ×{} → ×{}",
        "Calibrated": "Kalibrerad",
        "Raw": "Rå",
        "Measured vs real distance": "Uppmätt mot verkligt avstånd",
        "Which detected distance to show: calibrated (after correction) or raw (uncorrected)": "Vilket uppmätt avstånd som visas: kalibrerat (efter korrigering) eller rått (okorrigerat)",
        "measured-after-correction (real map distance)": "uppmätt efter korrigering (verkligt avstånd på kartan)",
        "Lines link receivers that measure each other. Colour = distance error (see legend); grey dashed = moved, recalibrate. Hover a line or receiver to read its detected (real) distance. The options below limit the count, filter by colour, and switch the detected distance between calibrated and raw. Click a line/pill to isolate, a receiver for its links. When both receivers have a mount height set (Height button on the receiver's row in the sidebar), the real distance is the true 3D distance between them.":
            "Linjerna förbinder mottagare som mäter varandra. Färg = avståndsfel (se förklaringen); grå streckad = flyttad, kalibrera om. Håll muspekaren över en linje eller mottagare för att se det uppmätta (verkliga) avståndet. Valen nedan begränsar antalet, filtrerar på färg och växlar mellan kalibrerat och rått avstånd. Klicka på en linje för att visa bara den, eller på en mottagare för dess linjer. När båda mottagarna har en monteringshöjd (linjalknappen i sidopanelen) är det verkliga avståndet det sanna 3D-avståndet.",
        "How many of each receiver's closest links to draw": "Hur många av varje mottagares närmaste linjer som ritas",
        "All links": "Alla linjer",
        "Closest 1": "Närmaste 1",
        "Closest 2": "Närmaste 2",
        "Closest 3": "Närmaste 3",
        "Closest 4": "Närmaste 4",
        "Closest 5": "Närmaste 5",
        "Show only links of this calibration colour": "Visa bara linjer med den här färgen",
        "All colours": "Alla färger",
        "Green — accurate": "Grön – träffsäker",
        "Red — too long": "Röd – för långt",
        "Blue — too short": "Blå – för kort",
        "Off — red & blue": "Fel – röd & blå",
        "accurate": "träffsäker",
        "too long": "för långt",
        "too short": "för kort",
        "moved since calibration — recalibrate": "flyttad sedan kalibreringen – kalibrera om",
        "No links match the current colour filter — pick a different colour or 'All colours'.": "Inga linjer matchar färgfiltret – välj en annan färg eller ”Alla färger”.",
        "Corrections applied to {} receiver(s).": "Korrigeringar tillämpade på {} mottagare.",
        "Corrections removed from {} receiver(s).": "Korrigeringar borttagna från {} mottagare.",
        "Remove calibration corrections from floor \"{}\"?": "Ta bort kalibreringskorrigeringarna för våningen ”{}”?",
        "Remove calibration corrections from floor \"{}\"? Auto calibration is on and will learn and re-apply them again.": "Ta bort kalibreringskorrigeringarna för våningen ”{}”? Automatisk kalibrering är på och kommer att lära sig och tillämpa dem igen.",
        "Save Floor Plan first — applying reloads the floor data and would discard your unsaved edits.": "Spara planritningen först – att tillämpa läser om våningen och skulle slänga osparade ändringar.",
        "Save Floor Plan first — resetting reloads the floor data and would discard your unsaved edits.": "Spara planritningen först – att återställa läser om våningen och skulle slänga osparade ändringar.",
        "Calibration failed: {}": "Kalibreringen misslyckades: {}",
        "Calibration request failed ({})": "Kalibreringsanropet misslyckades ({})",
        "No calibration data for this floor yet — run a calibration from the Calibration tab first.": "Ingen kalibreringsdata för våningen ännu – kör en kalibrering först.",
        "The floor's calibration data no longer matches its placed receivers (re-linked or renamed since the solve?) — run a new calibration.": "Våningens kalibreringsdata stämmer inte längre med de placerade mottagarna (omkopplade eller omdöpta sedan beräkningen?) – kör en ny kalibrering.",
        "data no longer matches the placed receivers": "data stämmer inte längre med de placerade mottagarna",
        "Check the probe is advertising its iBeacon (or sample longer).": "Kontrollera att mottagaren sänder sin iBeacon (eller samla längre).",
        "Placed on this floor but missing from this report": "Placerade på våningen men saknas i den här rapporten",
        "Placed since this report:": "Placerade efter den här rapporten:",
        "will be included on the next calibration run (auto mode re-solves every 15 minutes).": "tas med vid nästa kalibrering (automatiskt läge räknar om var 15:e minut).",
        "{} placed receiver{} missing — see below.": "{} placerade mottagare{} saknas – se nedan.",
        "· {} placed receiver{} missing — see below": "· {} placerade mottagare{} saknas – se nedan",
        "· {} placed receiver missing — see below": "· {} placerad mottagare saknas – se nedan",
        "· {} placed receivers missing — see below": "· {} placerade mottagare saknas – se nedan",
        "Matched, but no beacon samples:": "Matchade, men inga beacon-mätningar:",
        "No matching Bermuda scanner:": "Ingen matchande Bermuda-skanner:",
        "the scanner was found but produced no usable probe-to-probe adverts.": "skannern hittades men gav inga användbara mätningar mellan mottagarna.",
        "the device name no longer matches the placed id (usually a rename after moving the probe).": "enhetsnamnet stämmer inte längre med det placerade id:t (oftast ett namnbyte efter att mottagaren flyttats).",
        "Bermuda reports no scanners at all — is Bermuda installed, current, and seeing your proxies?": "Bermuda rapporterar inga skannrar alls – är Bermuda installerat, uppdaterat och ser dina proxyer?",
        "None of the {} placed receivers matched any of Bermuda's {} scanners": "Ingen av de {} placerade mottagarna matchade någon av Bermudas {} skannrar",
        "— re-link the receivers to their proxies (Debugging tab) and save.": "– koppla om mottagarna till sina proxyer (fliken Felsökning) och spara.",
        "Only {} of {} placed receivers matched a scanner; at least two are": "Bara {} av {} placerade mottagare matchade en skanner; minst två behövs",
        "needed to hear each other — re-link the rest (Debugging tab).": "för att de ska höra varandra – koppla om resten (fliken Felsökning).",
        "{} of {} placed receivers matched a scanner, but none of them is heard": "{} av {} placerade mottagare matchade en skanner, men ingen av dem hörs",
        "advertising an iBeacon — check the esp32_ble_beacon block on each proxy (see README) and": "sända en iBeacon – kontrollera blocket esp32_ble_beacon på varje proxy (se README) och",
        "that the proxies were re-flashed.": "att proxyerna har flashats om.",
        "{} of {} matched receivers are beaconing, but no sibling has heard": "{} av {} matchade mottagare sänder, men ingen annan har hört",
        "them recently — receivers may be out of range of each other.": "dem på senare tid – mottagarna kan vara utom räckhåll för varandra.",
        "⚠ Low confidence (aggressive correction or few pairs): {} — verify those receivers before applying.": "⚠ Låg säkerhet (kraftig korrigering eller få par): {} – kontrollera de mottagarna innan du tillämpar.",
        "against the true 3D distance — recalibrate after changing it.": "mot det sanna 3D-avståndet – kalibrera om efter en ändring.",
        "Used to remove the vertical leg from its distances and to judge calibration": "Används för att räkna bort höjdskillnaden från avstånden och för att bedöma kalibreringen",
        "recalibrate after changing it": "kalibrera om efter en ändring",

        // ---- placement advisor ----
        "Receiver placement": "Placering av mottagare",
        "Analyze": "Analysera",
        "Analyzing… this takes a few seconds.": "Analyserar… det tar några sekunder.",
        "Computing…": "Beräknar…",
        "Shows how precisely BPS can position someone across each floor with the receivers you have, and where one or two extra receivers would help most. Uses your floor plan, the receiver calibration above and the tracker zone history. Nothing is changed.":
            "Visar hur exakt BPS kan placera någon på varje våning med de mottagare du har, och var en eller två extra mottagare skulle göra mest nytta. Använder planritningen, mottagarkalibreringen ovan och zonhistoriken. Inget ändras.",
        "Expected error": "Förväntat fel",
        "suggested new receiver": "föreslagen ny mottagare",
        "receiver": "mottagare",
        "Zones, worst first": "Zoner, sämst först",
        "Time spent": "Tid",
        "Short visits": "Korta besök",
        "Most frequent jumps that came straight back:": "Vanligaste hoppen som direkt gick tillbaka:",
        "How is this calculated?": "Hur räknas det här?",
        "Where people are.": "Var folk är.",
        "Reading the numbers.": "Så läser du siffrorna.",
        "No receivers placed yet. Place receivers on the Map & Setup tab.": "Inga mottagare är placerade ännu. Placera mottagare under fliken Karta & inställning.",
        "No zones or receivers on this floor yet.": "Inga zoner eller mottagare på våningen ännu.",
        "No spot would make a meaningful difference — coverage is already even.": "Ingen plats skulle göra någon märkbar skillnad – täckningen är redan jämn.",
        "The analysis failed — see the Home Assistant log.": "Analysen misslyckades – se loggen i Home Assistant.",
        "No receiver calibration yet — using a generic noise model. Run calibration above for wall-aware results.": "Ingen mottagarkalibrering ännu – använder en generell brusmodell. Kör kalibreringen ovan för resultat som tar hänsyn till väggar.",
        "Noise model fitted on {} receiver pairs from the calibration.": "Brusmodellen är anpassad efter {} mottagarpar från kalibreringen.",
        "Weighted by {} h of tracker history from the recorder (last {} days).": "Viktat efter {} h spårningshistorik från recordern (senaste {} dagarna).",
        "Weighted by {} h of time in zones collected by BPS over {} day{} (keeps the last 14).": "Viktat efter {} h tid i zoner som BPS samlat under {} dag{} (sparar de senaste 14).",
        "No time-in-zone data yet — all zones weigh the same for now. BPS collects it from today, so re-run in a few days.": "Ingen data om tid i zoner ännu – alla zoner väger lika tills vidare. BPS samlar in den från i dag, så kör igen om några dagar.",
        "Lowers the expected error where people spend time on this floor from {} m to {} m.": "Sänker det förväntade felet där folk vistas på den här våningen från {} m till {} m.",
        "On top of #1, lowers the expected error where people spend time on this floor from {} m to {} m.": "Utöver #1 sänks det förväntade felet där folk vistas på den här våningen från {} m till {} m.",
        "In {} itself: {} → {} m.": "I {} självt: {} → {} m.",
        "{} of {}": "{} av {}",
        "A receiver near that boundary, or a longer zone dwell time, makes these go away.": "En mottagare nära den gränsen, eller längre tid innan zonbyte, får bort dem.",
        "Weighted by {} h of time in zones collected by BPS over {} day (keeps the last 14).": "Viktat efter {} h tid i zoner som BPS samlat under {} dag (sparar de senaste 14).",
        "Weighted by {} h of time in zones collected by BPS over {} days (keeps the last 14).": "Viktat efter {} h tid i zoner som BPS samlat under {} dagar (sparar de senaste 14).",
        "Re-analyze": "Analysera igen",
        "Zone": "Zon",
        "Receivers ≤ 6 m": "Mottagare ≤ 6 m",
        "Avg. distance": "Snittavstånd",
        "jumpy": "hoppig",
        "Average expected position error inside the zone": "Genomsnittligt förväntat positionsfel i zonen",
        "Receivers within 6 m of the zone centre": "Mottagare inom 6 m från zonens mitt",
        "Average distance from the zone centre to all receivers on the floor": "Snittavstånd från zonens mitt till alla mottagare på våningen",
        "Time trackers spent in the zone over the last {} days": "Tid spårarna var i zonen de senaste {} dagarna",
        "Visits shorter than a minute — a sign of position jitter": "Besök kortare än en minut – ett tecken på att positionen hoppar",
        "Lowers": "Sänker",
        "On top of #1, lowers": "Utöver #1 sänker",
        "{} the expected error where people spend time on this floor": "{} det förväntade felet där folk vistas på den här våningen",
        "the expected error where people spend time on this floor": "det förväntade felet där folk vistas på den här våningen",
        "No data yet.": "Ingen data ännu.",

        // ---- debugging ----
        "Receiver linking": "Mottagarkopplingar",
        "Scanner issues": "Skannerproblem",
        "How each placed receiver maps to its Bermuda distance sensors, and whether each is reporting a distance right now. Use this to tell a real naming mismatch (Unmatched) apart from a receiver that is linked correctly but simply not reporting at the moment (No reading). This is a live snapshot — press Refresh to re-check.":
            "Hur varje placerad mottagare kopplas till sina avståndssensorer i Bermuda och om de rapporterar ett avstånd just nu. Använd det för att skilja ett verkligt namnfel (Ej matchad) från en mottagare som är rätt kopplad men inte rapporterar för tillfället (Ingen mätning). Det är en ögonblicksbild – tryck på Uppdatera för att kontrollera igen.",
        "Each row is a tracked device (beacon) and the receivers reporting a live distance to it right now, closest first.": "Varje rad är en spårad enhet och de mottagare som rapporterar ett avstånd till den just nu, närmast först.",
        "Bermuda distance sensors (device: reading)": "Bermudas avståndssensorer (enhet: mätning)",
        "Receivers detecting it (closest first)": "Mottagare som hör den (närmast först)",
        "No beacons yet — tracked devices appear here once Bermuda reports a distance to them.": "Inga enheter ännu – spårade enheter visas här när Bermuda rapporterar ett avstånd till dem.",
        "No receiver currently detects this beacon.": "Ingen mottagare hör den här enheten just nu.",
        "Waiting for the first Bermuda dump…": "Väntar på första datan från Bermuda…",
        "No reading": "Ingen mätning",
        "Unmatched": "Ej matchad",
        "Live": "Live",
        "{} Live": "{} live",
        "{} No reading": "{} utan mätning",
        "{} Unmatched": "{} ej matchade",
        "Re-link": "Koppla om",
        "Refresh": "Uppdatera",
        "Receiver": "Mottagare",
        "Receivers": "Mottagare",
        "Status": "Status",
        "Hardware": "Hårdvara",
        "Beacons": "Beacons",
        "No zone": "Ingen zon",
        "no reading right now": "ingen mätning just nu",
        "Not reporting right now": "Rapporterar inte just nu",
        "not reporting": "rapporterar inte",
        "Not detected": "Inte hörd",
        "not found": "hittades inte",
        "No distance sensor carries this name": "Ingen avståndssensor har det här namnet",
        "No Bermuda sensor for “{}”{}": "Ingen Bermuda-sensor för ”{}”{}",
        "Linked, but no distance right now. See the": "Kopplad, men inget avstånd just nu. Se fliken",
        "tab for details.": "för detaljer.",
        "= no distance sensor carries that name at all; fix it with the": "= ingen avståndssensor har det namnet alls; rätta det med knappen",
        "button in the Map view’s “Scanner issues” panel, or rename the entity in Bermuda.": "i panelen ”Skannerproblem” på kartan, eller byt namn på entiteten i Bermuda.",
        "= the name matches a Bermuda distance sensor but it has no value right now — usually just no recent BLE contact, not a naming problem.": "= namnet matchar en avståndssensor i Bermuda men den har inget värde just nu – oftast bara ingen BLE-kontakt nyligen, inget namnproblem.",
        "= no receiver currently has a reading for it, usually because the device is off or out of range.": "= ingen mottagare har en mätning för den just nu, oftast för att enheten är avstängd eller utom räckhåll.",
        "Check the": "Kontrollera",
        "tab, or rename the device/entity so they match.": "fliken, eller byt namn på enheten/entiteten så att de matchar.",
        "Reporting a distance but not placed: {}": "Rapporterar avstånd men är inte placerad: {}",
        "Scanners with distance sensors but not placed on any floor": "Skannrar med avståndssensorer som inte är placerade på någon våning",
        "no match — remove or re-place": "ingen matchning – ta bort eller placera om",
        "— not this floor": "– inte den här våningen",
        "· on {} — not this floor": "· på {} – inte den här våningen",
        "· on": "· på",
        "Reflects unsaved edits — Save Floor Plan to apply them.": "Visar osparade ändringar – spara planritningen för att tillämpa dem.",
        "Error fetching BPS data:": "Fel när BPS-data hämtades:",
        "Failed to fetch BPS data:": "Kunde inte hämta BPS-data:",
        "Failed to fetch maps:": "Kunde inte hämta kartor:",
        "Failed loading tracker icons:": "Kunde inte läsa in spårningsikoner:",
        "Icon upload failed:": "Uppladdningen av ikonen misslyckades:",
        "Coordinates loaded:": "Koordinater inlästa:",
        "Updated data:": "Uppdaterad data:",

        // ---- settings ----
        "Features": "Funktioner",
        "Optional features, off by default. Turning one off stops it for everyone in the home.": "Valfria funktioner, avstängda från början. Stänger du av en stoppas den för alla i hemmet.",
        "Follow me": "Följ mig",
        "Music follows a person from room to room. Always opt-in per session: the person starts it from a notification or the app.": "Musiken följer en person från rum till rum. Alltid något man väljer själv: personen startar det från en notis eller appen.",
        "Follow me buttons for the dashboard": "Följ mig-knappar för dashboarden",
        "Suggestions": "Förslag",
        "Asks yes/no in a notification (e.g. dim the lights when the TV goes on) and learns from the answers.": "Frågar ja/nej i en notis (t.ex. dämpa ljuset när tv:n slås på) och lär sig av svaren.",
        "History": "Historik",
        "Notifications": "Notiser",
        "Open this page on tap": "Öppna den här sidan vid tryck",
        "Where the Home Assistant app opens when someone taps a BPS notification. Put a card for open questions on that page, so a question is never lost if the notification is dismissed.": "Vilken sida Home Assistant-appen öppnar när någon trycker på en BPS-notis. Lägg ett kort för öppna frågor på den sidan, så att en fråga aldrig försvinner om notisen stängs.",
        "Dashboard card (YAML)": "Kort för dashboarden (YAML)",
        "Dashboard → Edit → Add card → Manual, paste, save.": "Dashboard → Redigera → Lägg till kort → Manuellt, klistra in, spara.",
        "Card YAML copied.": "Kortets YAML är kopierad.",
        "Press Ctrl/Cmd+C to copy.": "Tryck Ctrl/Cmd+C för att kopiera.",
        "Bluetooth devices": "Bluetooth-enheter",
        "BPS needs one \"Distance to …\" sensor per receiver for every phone, watch or tag. Bermuda creates them turned off; turn them on here instead of one by one. A device only shows up here once Bermuda tracks it.": "BPS behöver en ”Distance to …”-sensor per mottagare för varje telefon, klocka eller tagg. Bermuda skapar dem avstängda; slå på dem här i stället för en och en. En enhet syns här först när Bermuda spårar den.",
        "Loading…": "Laddar…",
        "Manage distance sensors automatically": "Sköt avståndssensorerna automatiskt",
        "When you add a receiver, its distance sensors are turned on for every device that already has some on. If Bermuda can give BPS the distances directly, BPS turns the sensors off instead, and back on if that stops working.": "När du lägger till en mottagare slås dess avståndssensorer på för alla enheter som redan har några påslagna. Kan Bermuda ge BPS avstånden direkt stänger BPS i stället av sensorerna, och slår på dem igen om det slutar fungera.",
        "Could not read Bermuda's devices.": "Kunde inte läsa Bermudas enheter.",
        "Accuracy": "Träffsäkerhet",
        "Truth marks: you show BPS where a device really is, and BPS measures how far off it was. They also compare trilateration with fingerprint positioning (matching how the receivers hear the device against how they hear each other), so you can pick the mix that fits your house.": "Facitmarkeringar: du visar BPS var en enhet faktiskt är, och BPS mäter hur fel den låg. De jämför också trilaterering med fingeravtryck (hur mottagarna hör enheten jämfört med hur de hör varandra), så att du kan välja den blandning som passar ditt hus.",
        "It is actually here: click where this device really is": "Den är faktiskt här: klicka där enheten verkligen är",
        "Open the floor the device is on first.": "Öppna våningen enheten är på först.",
        "Click where {} really is.": "Klicka där {} verkligen är.",
        "Marked. Keep {} still for 45 seconds.": "Markerat. Låt {} ligga still i 45 sekunder.",
        "Could not save the mark: {}": "Kunde inte spara markeringen: {}",
        "Trilateration only": "Bara trilaterering",
        "Fingerprint only": "Bara fingeravtryck",
        "Mix, {} fingerprint": "Blandning, {} fingeravtryck",
        "Could not load the accuracy data.": "Kunde inte läsa träffsäkerheten.",
        "No fingerprint references yet: turn on Auto calibration above. The receivers measuring each other are the references.": "Inga fingeravtryck ännu: slå på Automatisk kalibrering ovan. Det är mottagarnas mätningar av varandra som blir fingeravtrycken.",
        "Fingerprint references: {}": "Fingeravtryck: {}",
        "In use: {} fingerprint": "Används nu: {} fingeravtryck",
        "In use: trilateration only": "Används nu: bara trilaterering",
        "Measuring {}: {} s left, {} readings. Keep it still.": "Mäter {}: {} s kvar, {} mätningar. Låt den ligga still.",
        "No marks yet. On the Map tab, press 📍 next to a tracked device and click where it really is.": "Inga markeringar ännu. Tryck på 📍 vid en spårad enhet under Karta och klicka där den verkligen är.",
        "Method": "Metod",
        "Typical error": "Typiskt fel",
        "Median over {} marks. Lower is better.": "Median av {} markeringar. Lägre är bättre.",
        "Use trilateration only": "Använd bara trilaterering",
        "Use {} fingerprint": "Använd {} fingeravtryck",
        "Marks": "Markeringar",
        "Device": "Enhet",
        "When": "När",
        "Trilateration": "Trilaterering",
        "Fingerprint": "Fingeravtryck",
        "{} on the wrong floor": "{} på fel våning",
        "Delete this mark": "Ta bort markeringen",
        "Could not save: {}": "Kunde inte spara: {}",
        "BPS reads the distances straight from Bermuda and has turned these sensors off to save load. If that stops working, BPS turns them back on by itself.": "BPS läser avstånden direkt från Bermuda och har stängt av de här sensorerna för att minska belastningen. Slutar det fungera slår BPS på dem igen av sig självt.",
        "BPS reads the distances straight from Bermuda, so these sensors aren't needed. BPS turns them off once that has worked for 10 minutes.": "BPS läser avstånden direkt från Bermuda, så de här sensorerna behövs inte. BPS stänger av dem när det har fungerat i 10 minuter.",
        "Bermuda is not installed. BPS gets its distances from Bermuda; install it from HACS first.": "Bermuda är inte installerat. BPS får sina avstånd från Bermuda; installera det från HACS först.",
        "Bermuda doesn't track any device yet. Add your phone, watch or tag in Bermuda first (see the wiki page Add a phone or watch).": "Bermuda spårar ingen enhet än. Lägg först till din telefon, klocka eller tagg i Bermuda (se wikisidan Add a phone or watch).",
        "{} of {} on": "{} av {} på",
        "{} turned off by you": "{} avstängda av dig",
        "Turn on {}": "Slå på {}",
        // ---- add a phone, watch or tag ----
        "+ Add a phone, watch or tag": "+ Lägg till telefon, klocka eller bricka",
        "Add a phone, watch or tag": "Lägg till telefon, klocka eller bricka",
        "Step {} of 5": "Steg {} av 5",
        "Close": "Stäng",
        "Back": "Tillbaka",
        "BPS can only place what Bermuda tracks. What do you want to add?": "BPS kan bara placera det som Bermuda spårar. Vad vill du lägga till?",
        "Android phone": "Android-telefon",
        "Companion app, 2 min": "Companion-appen, 2 min",
        "iPhone or iPad": "iPhone eller iPad",
        "Needs its IRK key, 10 min once": "Behöver sin IRK-nyckel, 10 min en gång",
        "Apple Watch": "Apple Watch",
        "Needs its own IRK key": "Behöver en egen IRK-nyckel",
        "Tag or other": "Bricka eller annat",
        "Key ring, collar, other watches": "Nyckelring, halsband, andra klockor",
        "Make it recognisable": "Gör den igenkännbar",
        "Checking…": "Kontrollerar…",
        "Bermuda is missing": "Bermuda saknas",
        "Find my device": "Hitta min enhet",
        "This is mine": "Det här är min",
        "Transmitter off": "Sändaren är av",
        "In the Home Assistant Companion app on the phone: Settings → Companion app → Manage sensors → BLE transmitter, and turn it on.": "I Home Assistant-appen på telefonen: Inställningar → Companion-app → Hantera sensorer → BLE-sändare, och slå på den.",
        "Phones with the Companion app:": "Telefoner med Home Assistant-appen:",
        "No phone with the BLE transmitter sensor yet.": "Ingen telefon med BLE-sändarsensorn än.",
        "Turned it on? Press Check again.": "Har du slagit på den? Tryck Kontrollera igen.",
        "Check again": "Kontrollera igen",
        "Apple devices change their Bluetooth address all the time. Home Assistant can follow them with the device's IRK key, in the Private BLE Device integration; Bermuda then tracks them by itself.": "Apple-enheter byter Bluetooth-adress hela tiden. Home Assistant kan följa dem med enhetens IRK-nyckel i integrationen Private BLE Device, och då spårar Bermuda dem av sig själv.",
        "Already added in Private BLE Device:": "Redan tillagda i Private BLE Device:",
        "Not sure which one is this device? Find it.": "Osäker på vilken som är den här enheten? Hitta den.",
        "No Private BLE Device yet.": "Ingen Private BLE Device än.",
        "Get the IRK: the wiki page Add a phone or watch shows two ways (a spare ESP32, or a Mac).": "Hämta IRK-nyckeln: wikisidan Add a phone or watch visar två sätt (ett extra ESP32-kort eller en Mac).",
        "Settings → Devices & services → Add integration → Private BLE Device, and paste it.": "Inställningar → Enheter och tjänster → Lägg till integration → Private BLE Device, och klistra in den.",
        "Open the wiki page": "Öppna wikisidan",
        "Adding a new Apple device": "Lägga till en ny Apple-enhet",
        "Add Private BLE Device": "Lägg till Private BLE Device",
        "Find your device": "Hitta din enhet",
        "Keep the device at least an arm's length from your receivers and press Start. Then hold it right against one of them for about 30 seconds.": "Ha enheten minst en armlängd från dina mottagare och tryck Starta. Håll den sedan tätt intill en av dem i ungefär 30 sekunder.",
        "Phones: unlock the screen now and then, so it keeps sending.": "Telefoner: lås upp skärmen då och då så att den fortsätter sända.",
        "Start": "Starta",
        "Starting…": "Startar…",
        "Try again": "Försök igen",
        "{} m from {}": "{} m från {}",
        "(was {} m)": "(var {} m)",
        "This one": "Den här",
        "Changing address: set up its IRK first (step 2).": "Byter adress: lägg in dess IRK-nyckel först (steg 2).",
        "Keep holding it against the receiver…": "Håll kvar den intill mottagaren…",
        "Done looking.": "Sökningen är klar.",
        "Nothing has come close yet.": "Inget har kommit nära än.",
        "Nothing came close. Is the device on and near a receiver? Android: is the BLE transmitter on?": "Inget kom nära. Är enheten på och nära en mottagare? Android: är BLE-sändaren på?",
        "Apple device (IRK)": "Apple-enhet (IRK)",
        "Fixed address": "Fast adress",
        "Changing address": "Byter adress",
        "Add it to Bermuda": "Lägg till i Bermuda",
        "Bermuda doesn't track {} yet. BPS can add it for you: this adds {} to Bermuda's Configure → Select devices, and Bermuda restarts itself.": "Bermuda spårar inte {} än. BPS kan lägga till den åt dig: {} läggs till under Bermudas Konfigurera → Select devices, och Bermuda startar om sig själv.",
        "Add to Bermuda": "Lägg till i Bermuda",
        "Could not change Bermuda's settings: {}": "Kunde inte ändra Bermudas inställningar: {}",
        "Turning on its distance sensors": "Slår på dess avståndssensorer",
        "Waiting for Bermuda to create the device's distance sensors. This usually takes under a minute.": "Väntar på att Bermuda skapar enhetens avståndssensorer. Det brukar ta under en minut.",
        "Still waiting. A receiver must hear the device before Bermuda creates its sensors: keep it near one. You can close this; the device then shows up under Bluetooth devices.": "Väntar fortfarande. En mottagare måste höra enheten innan Bermuda skapar dess sensorer, så håll den nära en. Du kan stänga det här; enheten dyker då upp under Bluetooth-enheter.",
        "Link it to a person": "Koppla till en person",
        "{} is tracked: {} of {} distance sensors on.": "{} spåras: {} av {} avståndssensorer på.",
        "Whose is it? BPS then places that person with it. In about a minute it also shows up under Map & Setup → Tracking.": "Vems är den? BPS placerar då den personen med den. Om ungefär en minut syns den också under Karta & inställning → Spårning.",
        "Link and save": "Koppla och spara",
        "Turned on {} distance sensors. Home Assistant reloads Bermuda in about 30 seconds; then the device shows up under Map & Setup → Tracking.": "Slog på {} avståndssensorer. Home Assistant laddar om Bermuda om ungefär 30 sekunder; sedan syns enheten under Karta & inställning → Spårning.",
        "Could not turn the sensors on.": "Kunde inte slå på sensorerna.",
        "Persons": "Personer",
        "Link each person to their BPS trackers, best first. The first usable tracker decides the person's zone; one that is charging, not seen, or lying still while a lower one moves is skipped. Result: sensor.bps_person_<name>_zone.": "Koppla varje person till sina BPS-spårare, bäst först. Den första användbara spåraren avgör personens zon; en som laddar, inte syns eller ligger still medan en lägre rör sig hoppas över. Resultat: sensor.bps_person_<namn>_zone.",
        "No people in Home Assistant yet (Settings → People).": "Inga personer i Home Assistant ännu (Inställningar → Personer).",
        "No trackers linked.": "Inga spårare kopplade.",
        "+ Add tracker…": "+ Lägg till spårare…",
        "no charging sensor": "ingen laddsensor",
        "Advanced timing": "Avancerad tidsinställning",
        "Zone must hold (s)": "Zonen måste hålla (s)",
        "Still after (min)": "Stilla efter (min)",
        "Recent move (s)": "Nyligen rörd (s)",
        "Move threshold (m)": "Rörelsegräns (m)",
        "Not seen after (s)": "Inte sedd efter (s)",
        "Enter a number between {} and {}.": "Ange ett tal mellan {} och {}.",
        "Access": "Åtkomst",
        "Everyone in Home Assistant can open BPS. By default only administrators can change it; other users only see what is meant for them. Only an administrator can change this setting.": "Alla i Home Assistant kan öppna BPS. Från början kan bara administratörer ändra det; andra användare ser bara det som är till för dem. Bara en administratör kan ändra den här inställningen.",
        "Full access for all users": "Full åtkomst för alla användare",
        "When on, every Home Assistant user, not only administrators, can change floor plans, zones, calibration and these settings. Learned patterns stay private: each user only ever sees their own.": "När det är på kan alla användare i Home Assistant, inte bara administratörer, ändra planritningar, zoner, kalibrering och de här inställningarna. Inlärda mönster förblir privata: varje användare ser bara sina egna.",
        "Save settings": "Spara inställningar",
        "Unsaved changes": "Osparade ändringar",
        "Settings saved.": "Inställningarna är sparade.",
        "Could not save settings.": "Kunde inte spara inställningarna.",
        "Could not load BPS settings.": "Kunde inte läsa in BPS-inställningarna.",
        "You don't have access to change BPS settings.": "Du har inte behörighet att ändra BPS-inställningarna.",
        "Not saved: {}": "Inte sparat: {}",
        "Not saved:": "Inte sparat:",
        "active": "aktiv",
        "not seen": "inte sedd",
        "charging": "laddar",
        "still": "stilla",
        "standby": "reserv",
        "wearable": "bärbar",
        "watch": "klocka",
        "phone": "telefon",
        "tag": "tagg",
        "automatic ({})": "automatiskt ({})",
        "automatic (none found)": "automatiskt (ingen hittad)",
        "no zone": "ingen zon",
        "still {} min": "stilla {} min",
        "none found": "ingen hittad",
        "📍 {}": "📍 {}",

        // ---- learned ----
        "Learning": "Inlärning",
        "Ready": "Redo",
        "Learning: {} of {} days": "Lär sig: {} av {} dagar",
        "{} days with data in the last 60 days. Enough to find routines.": "{} dagar med data de senaste 60 dagarna. Det räcker för att hitta rutiner.",
        "{} more day with someone at home before BPS suggests routines on its own.": "{} dag till med någon hemma innan BPS föreslår rutiner på egen hand.",
        "{} more days with someone at home before BPS suggests routines on its own.": "{} dagar till med någon hemma innan BPS föreslår rutiner på egen hand.",
        "Data since {}.": "Data sedan {}.",
        "History is turned off (Settings → Features), so BPS is not learning.": "Historik är avstängt (Inställningar → Funktioner), så BPS lär sig inget.",
        "No suggestions yet.": "Inga förslag ännu.",
        "Suggestions are turned off in Settings → Features.": "Förslag är avstängda under Inställningar → Funktioner.",
        "Nobody has been asked yet.": "Ingen har fått frågan ännu.",
        "Asks": "Frågar",
        "Automatic": "Automatiskt",
        "Never": "Aldrig",
        "Ask instead": "Fråga i stället",
        "Allow again": "Tillåt igen",
        "Forget": "Glöm",
        "{} yes · {} no": "{} ja · {} nej",
        "{} of 3 yes in a row": "{} av 3 ja i rad",
        "last asked {}": "senast frågad {}",
        "(when someone unidentified is in the room)": "(när någon okänd är i rummet)",
        "(someone unidentified was in the room)": "(någon okänd var i rummet)",
        "Everyone": "Alla",
        "Today": "I dag",
        "Saved.": "Sparat.",
        "What happens on yes": "Det här händer vid ja",
        "Only lights linked to {} (Zone links → Lights).": "Bara lampor som är länkade till {} (Zonlänkar → Lampor).",
        "Own extras": "Egna tillägg",
        "Run only when a ticked person says yes (or it runs automatically for them).": "Körs bara när en ikryssad person svarar ja (eller när det körs automatiskt för hen).",
        "None yet.": "Inga ännu.",
        "No lights.": "Inga lampor.",
        "+ Add extra": "+ Lägg till",
        "Applies to:": "Gäller:",
        "Include": "Ta med",
        "Reset": "Återställ",
        "Remove": "Ta bort",
        "Add": "Lägg till",
        "changed from {}": "ändrad från {}",
        "not linked to the zone, skipped": "inte länkad till zonen, hoppas över",
        "Undo doesn't restore this": "Ångra återställer inte",
        "BPS starts it when you say yes. Undo only restores lights and speakers, not what this changes.": "BPS startar den när du svarar ja. Ångra återställer bara lampor och högtalare, inte det som den här ändrar.",
        "All speakers (whole house)": "Alla högtalare (hela huset)",
        "Light": "Lampa",
        "Speaker": "Högtalare",
        "Script, scene or automation": "Script, scen eller automation",
        "Mute": "Tysta",
        "Pause": "Pausa",
        "Volume": "Volym",
        "volume {} %": "volym {} %",
        "0 = off": "0 = av",
        "off": "av",
        "on": "på",
        "muted": "tyst",
        "paused": "pausad",
        "runs": "körs",
        "colour": "färg",
        "At least one person must be ticked. Use Remove to delete it.": "Minst en person måste vara ikryssad. Använd Ta bort för att radera tillägget.",
        "Lights": "Lampor",
        "Link HA area, media players, presence sensors and lights": "Länka HA-område, mediaspelare, närvarosensorer och lampor",
        "text changed here": "text ändrad här",
        "Edit text": "Ändra text",
        "Save": "Spara",
        "Title": "Rubrik",
        "Question": "Fråga",
        "Text when it ran automatically": "Text när det körts automatiskt",
        "Question when only someone unidentified is in the room": "Fråga när bara någon okänd är i rummet",
        "From the automation: {}": "Från automationen: {}",
        "Text changed here wins over the automation's. Leave a field empty to use the automation's text.": "Text som ändras här gäller före automationens. Lämna ett fält tomt för att använda automationens text.",
        "Use the automation's text": "Använd automationens text",
        "The only lights a suggestion for this zone may change": "De enda lampor som ett förslag för den här zonen får ändra",
        "Could not load what BPS has learned. Try again in a moment.": "Kunde inte läsa in vad BPS har lärt sig. Försök igen om en stund.",
        "Nothing yet. Questions, answers and follow-me sessions show up here.": "Inget ännu. Frågor, svar och Följ mig-sessioner visas här.",
        "BPS learns routines from its local history (Settings → History). It needs 14 days with data, days when someone was home, before it suggests anything on its own. Days away don't count.": "BPS lär sig rutiner från sin lokala historik (Inställningar → Historik). Den behöver 14 dagar med data, dagar då någon var hemma, innan den föreslår något på egen hand. Dagar borta räknas inte.",
        "Each suggestion BPS has made, per person: Asks (asks every time), Automatic (said yes 3 times in a row, now just happens, with an Undo button), or Never (said \"Don't ask again\"). Change it here at any time.": "Varje förslag BPS har gjort, per person: Frågar (frågar varje gång), Automatiskt (sa ja 3 gånger i rad, sker nu direkt, med en Ångra-knapp) eller Aldrig (sa ”Fråga inte igen”). Du kan ändra det här när som helst.",
        "The last 30 days of questions, answers, automatic runs and follow-me sessions.": "De senaste 30 dagarnas frågor, svar, automatiska körningar och Följ mig-sessioner.",
        "Floor plans, calibration and settings are managed by a Home Assistant administrator. Here you see what BPS has asked you and learned about you; nobody else's.": "Planritningar, kalibrering och inställningar sköts av en administratör i Home Assistant. Här ser du vad BPS har frågat dig och lärt sig om dig – ingen annans.",
        "was asked": "fick frågan",
        "said yes": "sa ja",
        "said no": "sa nej",
        "said don't ask again": "sa fråga inte igen",
        "undid it": "ångrade",
        "it ran automatically": "det kördes automatiskt",
        "no answer": "inget svar",
        "on the dashboard": "på dashboarden",
        "(30 min passed)": "(30 min gick)",
        "(the moment passed)": "(tillfället passerade)",
        "forgot it (Learned tab)": "glömde det (fliken Lärt sig)",
        "allowed asking again (Learned tab)": "tillät frågan igen (fliken Lärt sig)",
        "stopped automatic (Learned tab)": "stängde av automatiskt (fliken Lärt sig)",
        "turned it off (Learned tab)": "stängde av det (fliken Lärt sig)",
        "Follow me?": "Följ mig?",
        "Follow me? ({})": "Följ mig? ({})",
        ": follow me started": ": Följ mig startade",
        ": follow me started ({})": ": Följ mig startade ({})",
        ": follow me stopped": ": Följ mig stoppades",
        ": follow me stopped ({})": ": Följ mig stoppades ({})",
        ": music followed into {}": ": musiken följde med till {}",
        ": music left {}": ": musiken lämnade {}",
        ": follow me {}": ": Följ mig {}",
        "manual": "manuellt",
        "notification": "notis",
        "left home": "lämnade hemmet",
        "feature off": "funktionen avstängd",
        "removed": "borttagen",
    } };

    // Paragraphs with inline markup, by data-i18n key.
    const HTML = { sv: {
        "accuracy-lead": 'Hur fel ligger BPS, i meter? Tryck på 📍 vid en spårad enhet under Karta, klicka där den verkligen är och låt den ligga still i 45 sekunder. Varje markering mäter trilatereringen, fingeravtrycket och blandningar av dem. Markeringar i olika rum ger det rättvisaste svaret.',
        "placement-lead": 'Var skulle en mottagare till göra mest nytta? Röda områden är där BPS har svårt att placera folk; stjärnorna är de bästa platserna för en ny mottagare, rangordnade efter hur mycket de förbättrar precisionen <i>där folk faktiskt vistas</i>.',
        "placement-how": '<p><b>Avstånd.</b> En mottagares avståndsuppskattning har ett fel som är ungefär en fast <i>andel</i> av avståndet, så mottagare långt bort bidrar lite. Hur stor andelen är kommer från din egen mottagarkalibrering: mottagarna mäter varandra på kända avstånd, vilket fångar väggar, bjälklag och montering. En mottagare som genomgående mäter sämre än de andra får mindre vikt.</p>'
            + '<p><b>Geometri.</b> Det räcker inte att vara nära mottagare; de behöver omge dig. Tre mottagare på rad på ena sidan ger en dålig position även när de är nära, ungefär som GPS-satelliter samlade i en del av himlen. Kartan väger samman avstånd, antal mottagare inom räckhåll och hur de sprids runt varje punkt till ett förväntat fel.</p>'
            + '<p><b>Var folk är.</b> Varje zon viktas efter hur länge spårarna var där, så en bättre position i köket väger tyngre än i ett förråd. Korta besök som studsar direkt tillbaka till förra zonen listas som en verklighetskontroll: så ser bristande precision ut i vardagen.</p>'
            + '<p><b>Förslag.</b> En tänkt mottagare provas på varje meter inuti zonerna; platsen som sänker det tidsviktade felet mest vinner, sedan den bästa andra platsen givet den första. Stjärnor kan hamna på opraktiska ställen (en balkong inuti en zon, mitt i ett rum): använd närmaste vägg med ström.</p>'
            + '<p><b>Så läser du siffrorna.</b> Metrarna kommer från en förenklad modell och är i överkant; rangordningen och den relativa förbättringen är det du ska agera på. Kör igen efter att du flyttat eller lagt till en mottagare och kalibrerat om.</p>',
        "notify-help": 'BPS ställer sina frågor som notiser i Home Assistant-appen. En stängd eller missad notis får inte göra att frågan försvinner, så BPS håller också den öppna frågan i <code>sensor.bps_suggestion</code> (läget <code>ask</code> medan en fråga väntar, med <code>title</code> och <code>text</code>). Lägg kortet nedan på sidan ovan: det syns bara medan en fråga är öppen, och knapparna svarar som den person som trycker.',
        "follow-help": 'Varje person får <code>sensor.bps_follow_&lt;person&gt;</code>: <code>available</code> medan musik spelar i zonen personen är i och ingen annan äger den, <code>active</code> medan musiken följer personen, annars <code>off</code>. När musik startar nära någon frågar BPS också i en notis. Kortet nedan visar <b>Följ mig</b> bara för personen det gäller, och bara medan det är tillgängligt, och <b>Sluta följa</b> medan det är aktivt. Knapparna anropar <code>bps.follow_me_start</code> / <code>bps.follow_me_stop</code>, som gäller den som trycker. Personer behöver en användare i Home Assistant och minst en spårare (se Personer nedan); YAML-koden byggs från dina personinställningar, så spara dem först.',
        "history-help": '<b>Historik</b> <span class="bps-links-hint">Sparar en lokal logg över zonbyten och manuella ändringar av lampor, spelare, rullgardiner och klimat (vem, var, när), för historiken och för att lära sig rutiner. Sparas i <code>bps_data/</code> bara på den här Home Assistant, i 3 månader. Stäng av för att sluta samla in; Följ mig och förslag fortsätter att fungera.</span>',
    } };

    const SKIP = new Set(["SCRIPT", "STYLE", "CODE", "PRE", "TEXTAREA"]);
    let lang = "en";
    let dict = null;
    let patterns = [];

    function norm(s) { return s.replace(/\s+/g, " ").trim(); }
    function escapeRe(s) { return s.replace(/[.*+?^$()|[\]\\]/g, "\\$&"); }

    function compile(d) {
        patterns = Object.keys(d).filter((k) => k.includes("{}")).map((k) => ({
            re: new RegExp("^" + k.split("{}").map(escapeRe).join("(.*?)") + "$", "s"),
            out: d[k],
        }));
    }

    function translate(text) {
        if (!dict) return null;
        const key = norm(text);
        if (!key || !/[A-Za-z]/.test(key)) return null;
        if (Object.prototype.hasOwnProperty.call(dict, key)) return dict[key];
        for (const p of patterns) {
            const m = key.match(p.re);
            if (m) {
                let i = 1;
                return p.out.replace(/\{\}/g, () => (m[i++] || ""));
            }
        }
        return null;
    }

    function t(text, ...args) {
        let out = (dict && Object.prototype.hasOwnProperty.call(dict, text)) ? dict[text] : text;
        if (args.length) out = out.replace(/\{\}/g, () => String(args.length ? args.shift() : ""));
        return out;
    }

    function fixNode(node) {
        const v = node.nodeValue;
        const tr = translate(v);
        if (tr == null || tr === norm(v)) return;
        const lead = v.match(/^\s*/)[0];
        const trail = v.match(/\s*$/)[0];
        node.nodeValue = lead + tr + trail;
    }

    function fixAttrs(el) {
        for (const a of ["title", "placeholder", "aria-label"]) {
            const v = el.getAttribute && el.getAttribute(a);
            if (v) {
                const tr = translate(v);
                if (tr != null && tr !== v) el.setAttribute(a, tr);
            }
        }
        const key = el.getAttribute && el.getAttribute("data-i18n");
        if (key && HTML[lang] && HTML[lang][key] && !el.__bpsI18n) {
            el.__bpsI18n = true;
            el.innerHTML = HTML[lang][key];
        }
    }

    function walk(root) {
        if (!dict || !root) return;
        if (root.nodeType === 3) {
            if (!root.parentElement || !SKIP.has(root.parentElement.tagName)) fixNode(root);
            return;
        }
        if (root.nodeType !== 1) return;
        if (SKIP.has(root.tagName)) { if (root.tagName === "TEXTAREA") fixAttrs(root); return; }
        fixAttrs(root);
        const tw = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
            acceptNode: (n) => {
                if (n.nodeType === 1 && SKIP.has(n.tagName)) {
                    if (n.tagName === "TEXTAREA") fixAttrs(n);   // placeholder yes, content no
                    return NodeFilter.FILTER_REJECT;
                }
                return NodeFilter.FILTER_ACCEPT;
            },
        });
        let n = tw.nextNode();
        while (n) {
            if (n.nodeType === 3) fixNode(n); else fixAttrs(n);
            n = tw.nextNode();
        }
    }

    let observer = null;
    function observe() {
        if (observer || !dict) return;
        observer = new MutationObserver((muts) => {
            observer.disconnect();
            for (const m of muts) {
                if (m.type === "childList") m.addedNodes.forEach(walk);
                else if (m.type === "characterData") walk(m.target);
                else if (m.type === "attributes") fixAttrs(m.target);
            }
            observer.observe(document.body, OPTS);
        });
        observer.observe(document.body, OPTS);
    }
    const OPTS = { childList: true, subtree: true, characterData: true, attributes: true,
                   attributeFilter: ["title", "placeholder", "aria-label"] };

    function setLanguage(code) {
        const l = String(code || "en").split("-")[0].toLowerCase();
        if (l === lang) return;
        if (!TEXT[l]) { lang = "en"; return; }   // switching back to English needs a reload
        lang = l;
        dict = {};
        for (const [k, v] of Object.entries(TEXT[l])) dict[norm(k)] = v;
        compile(dict);
        document.documentElement.lang = l;
        const run = () => { walk(document.body); observe(); };
        if (document.body) run(); else document.addEventListener("DOMContentLoaded", run);
    }

    window.bpsI18n = { t, setLanguage, get language() { return lang; } };
    window.bpsT = t;
    // The panel passes the HA user's language in with the access token
    // (script.js calls setLanguage). Opened outside the panel: use the browser's.
    let chosen = false;
    window.bpsI18n.choose = (code) => { chosen = true; setLanguage(code); };
    setTimeout(() => { if (!chosen) setLanguage(navigator.language || "en"); }, 3000);
})();
