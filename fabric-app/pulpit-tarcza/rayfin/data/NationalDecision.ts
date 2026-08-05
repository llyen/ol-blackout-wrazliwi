import { entity, role, text, int, date, uuid } from '@microsoft/rayfin-core';

/**
 * Decyzja szczebla krajowego (Ekran 1 - Decydent krajowy).
 *
 * Rejestr decyzji jest dowodem w rozliczeniu dzialan, wiec nie ma roli z akcja
 * 'delete' ani 'update' - raz zapisana decyzja zostaje. Odwolanie decyzji to
 * nowy wpis o typie `odwolanie` wskazujacy poprzedni w polu `supersedes`.
 */
@entity()
@role('authenticated', ['create', 'read'])
export class NationalDecision {
  @uuid() id!: string;
  /** Identyfikator nadawany w aplikacji, np. DEC-2026-01-16-004. */
  @text({ min: 3, max: 40 }) decision_id!: string;
  /** Chwila sceny, ktorej dotyczy decyzja (ISO 8601). */
  @text({ max: 30 }) scene_time!: string;
  /**
   * 'zwolanie_RZZK' | 'uruchomienie_SPO-5' | 'uruchomienie_SPO-12' |
   * 'wniosek_o_wsparcie_SZ' | 'stan_kleski' | 'odwolanie'.
   */
  @text({ min: 3, max: 40 }) decision_type!: string;
  /** 'kraj' albo kod wojewodztwa. */
  @text({ max: 40 }) scope!: string;
  /** Liczba gmin krytycznych w chwili decyzji - kontekst dla audytu. */
  @int() critical_gminas!: number;
  /** Osoby wrazliwe bez zasilania w chwili decyzji. */
  @int() vulnerable_without_power!: number;
  @text({ min: 20, max: 1500 }) justification!: string;
  /** Identyfikator decyzji, ktora ta decyzja odwoluje lub zmienia. */
  @text({ max: 40 }) supersedes!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
