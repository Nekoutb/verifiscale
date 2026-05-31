import { PlaceholderModule } from '@/components/placeholder-module';

export default function IntegritePage() {
  return (
    <PlaceholderModule
      title="Intégrité des écritures comptables"
      description="Vérifications individuelles pièce par pièce (partie double, chronologie, pièce justificative)."
      upcomingControls={[
        { code: 'A1',  label: 'Équilibre individuel des écritures (partie double)',           ref: 'SYSCOHADA art. 17.2' },
        { code: 'A2',  label: 'Pièce justificative datée pour chaque ligne',                  ref: 'SYSCOHADA art. 17.3' },
        { code: 'A3',  label: 'Chronologie sans insertion intercalaire post-clôture',         ref: 'SYSCOHADA art. 16 + 22' },
        { code: 'A4',  label: 'Identification ligne par ligne (origine, imputation, contenu)', ref: 'SYSCOHADA art. 17.5' },
        { code: 'A12', label: 'Corrections d\'erreur significative N-x → report à nouveau',   ref: 'SYSCOHADA art. 20' },
      ]}
    />
  );
}
