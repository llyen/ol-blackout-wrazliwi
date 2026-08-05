import { entity, role, text, decimal, date, uuid } from '@microsoft/rayfin-core';

/**
 * Wynik wizyty kontrolnej u osoby z listy priorytetowej (Ekran 3 - Gmina/OSP).
 *
 * **Nie zapisujemy tu zadnych danych osobowych.** Osoba jest identyfikowana
 * wylacznie tokenem `PRIO-xxxxx`; imie, adres i telefon zostaja w warstwie
 * zrodlowej, do ktorej aplikacja nie ma dostepu. Notatka ma limit 500 znakow
 * i jest opisem sytuacji technicznej, nie stanu zdrowia.
 *
 * `offline_sync_id` nadaje urzadzenie terenowe przed wyslaniem. Sluzy do
 * rozpoznania powtorzonego zapisu po odzyskaniu lacznosci - ten sam identyfikator
 * oznacza ten sam wynik, a nie druga wizyte.
 */
@entity()
@role('authenticated', ['create', 'read'])
export class WelfareVisitResult {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) visit_result_id!: string;
  @text({ max: 30 }) scene_time!: string;
  /** Token osoby z listy priorytetowej - bez danych identyfikujacych. */
  @text({ min: 3, max: 30 }) person_token!: string;
  /** Kategoria medyczna z listy priorytetowej, np. home_oxygen. */
  @text({ max: 40 }) category!: string;
  @text({ min: 4, max: 12 }) gmina_code!: string;
  @text({ max: 120 }) gmina_name!: string;
  @text({ min: 2, max: 30 }) team_id!: string;
  /**
   * 'contact_confirmed' | 'no_contact' | 'evacuation' | 'generator_needed'.
   */
  @text({ min: 3, max: 30 }) result!: string;
  /** Wymagane przy wyniku `evacuation` - walidacja po stronie aplikacji. */
  @text({ max: 160 }) destination!: string;
  /** Pozostala autonomia urzadzenia medycznego w chwili wizyty (godziny). */
  @decimal() autonomy_hours_left!: number;
  @text({ max: 500 }) notes!: string;
  /** Identyfikator nadany przez urzadzenie terenowe - klucz odsiewania duplikatow. */
  @text({ max: 60 }) offline_sync_id!: string;
  /** 'online' | 'offline' - tryb, w ktorym powstal zapis. */
  @text({ max: 20 }) capture_mode!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
