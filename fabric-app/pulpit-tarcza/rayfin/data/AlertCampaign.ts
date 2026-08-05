import { entity, role, text, int, date, uuid } from '@microsoft/rayfin-core';

/**
 * Kampania ostrzegawcza SPO-3 (Ekran 5 - Komunikacja).
 *
 * Kampania po zatwierdzeniu jest dokumentem - stad brak akcji 'delete'.
 * Aktualizacja sluzy wylacznie wznowieniu wysylki do gmin, ktore nie odebraly
 * komunikatu, i jest ograniczona do autora.
 */
@entity()
@role('authenticated', ['create', 'read'])
@role('authenticated', ['update'], {
  policy: (claims, item) => claims.sub.eq(item.author_id),
})
export class AlertCampaign {
  @uuid() id!: string;
  @text({ min: 3, max: 40 }) campaign_id!: string;
  @text({ max: 30 }) scene_time!: string;
  /** Tresc komunikatu. Dolna granica wynika z wymogow SPO-3 co do zawartosci. */
  @text({ min: 160, max: 600 }) message_text!: string;
  /** Kanaly rozdzielone przecinkiem: RSO, SMS, local_radio, WWW, social. */
  @text({ min: 3, max: 120 }) channels!: string;
  /** Kody gmin rozdzielone przecinkiem. */
  @text({ min: 4, max: 4000 }) target_gminas!: string;
  @int() target_gmina_count!: number;
  /** Laczna populacja gmin objetych kampania. */
  @int() target_population!: number;
  /** Gminy o pokryciu telekomunikacyjnym ponizej 20% - tam RSO i SMS nie dotra. */
  @int() low_coverage_gminas!: number;
  /** 'szkic' | 'zatwierdzona' | 'wyslana' | 'wznowiona'. */
  @text({ min: 3, max: 20 }) approval_status!: string;
  @text({ max: 10 }) language!: string;
  /** 'kraj' albo kod wojewodztwa - zasieg uprawnien autora. */
  @text({ max: 40 }) scope!: string;
  @text({ max: 120 }) author_id!: string;
  @text({ max: 160 }) author_name!: string;
  @text({ min: 3, max: 40 }) author_role!: string;
  @date() created_at!: Date;
}
