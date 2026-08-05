import { entity, role, text, int, decimal, date, uuid } from '@microsoft/rayfin-core';

/**
 * Przydzial agregatu do punktu grzewczego albo placowki opieki (Ekran 2 - Wojewoda).
 *
 * Wojewoda moze zmienic wlasny przydzial dopoki nie zostal potwierdzony w terenie,
 * dlatego aktualizacja jest ograniczona polityka do autora wpisu.
 */
@entity()
@role('authenticated', ['create', 'read'])
@role('authenticated', ['update'], {
  policy: (claims, item) => claims.sub.eq(item.author_id),
})
export class GeneratorAssignment {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) assignment_id!: string;
  @text({ max: 30 }) scene_time!: string;
  @text({ min: 3, max: 30 }) generator_id!: string;
  /** 'heating_point' | 'care_facility'. */
  @text({ min: 3, max: 30 }) target_type!: string;
  @text({ min: 3, max: 30 }) target_id!: string;
  @text({ max: 160 }) target_name!: string;
  @text({ min: 4, max: 12 }) gmina_code!: string;
  @text({ max: 120 }) gmina_name!: string;
  @text({ max: 4 }) voivodeship_code!: string;
  @int() power_kw!: number;
  /** Zapotrzebowanie celu - roznica wzgledem `power_kw` mowi, czy moc wystarcza. */
  @decimal() power_need_kw!: number;
  @int() eta_minutes!: number;
  /** Liczba osob wrazliwych objetych przydzialem - uzasadnienie priorytetu. */
  @int() covered_vulnerable!: number;
  /** 'zatwierdzony' | 'zmieniony' | 'odrzucony' | 'wniosek_o_wiecej'. */
  @text({ min: 3, max: 30 }) status!: string;
  /** Wymagany przy zmianie i odrzuceniu - walidacja po stronie aplikacji. */
  @text({ max: 1200 }) comment!: string;
  /** Agregat pierwotnie rekomendowany przez model - do porownania z decyzja. */
  @text({ max: 30 }) recommended_generator_id!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
