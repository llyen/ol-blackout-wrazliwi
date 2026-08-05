import { entity, role, text, int, boolean, decimal, date, uuid } from '@microsoft/rayfin-core';

/**
 * Raport z punktu grzewczego (Ekran 4 - Punkt grzewczy).
 *
 * Raport jest skladany cyklicznie, wiec kazdy wpis to osobny rekord - historia
 * obledania i zapotrzebowania jest tresc, nie szum. Stad brak akcji 'update'.
 */
@entity()
@role('authenticated', ['create', 'read'])
export class HeatingPointReport {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) report_id!: string;
  @text({ max: 30 }) scene_time!: string;
  @text({ min: 3, max: 30 }) heating_point_id!: string;
  @text({ min: 4, max: 12 }) gmina_code!: string;
  @text({ max: 120 }) gmina_name!: string;
  @text({ max: 4 }) voivodeship_code!: string;
  /** 'planned' | 'open' | 'full' | 'closed'. */
  @text({ min: 3, max: 20 }) status!: string;
  @int() occupancy!: number;
  @int() capacity!: number;
  @boolean() needs_food!: boolean;
  @boolean() needs_medical_support!: boolean;
  @boolean() needs_generator!: boolean;
  @decimal() fuel_hours_remaining!: number;
  /** Wymagany, gdy obledanie przekracza pojemnosc - walidacja w aplikacji. */
  @text({ max: 600 }) comment!: string;
  /** Pozycje checklisty otwarcia, ktore nie zostaly odhaczone. */
  @text({ max: 600 }) checklist_gaps!: string;
  @text({ max: 60 }) offline_sync_id!: string;
  @text({ max: 20 }) capture_mode!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
