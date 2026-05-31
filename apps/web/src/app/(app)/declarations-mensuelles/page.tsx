import { PlaceholderModule } from '@/components/placeholder-module';

export default function MonthlyPage() {
  return (
    <PlaceholderModule
      title="Rapprochement des déclarations mensuelles"
      description="TVA (4431/4452), IRPP retenu (4471), CNPS (4311), acompte IS (4441) — rapprochés au grand livre."
      upcomingControls={[
        { code: 'D1',  label: 'Taux TVA général = 17,5 % (CAC inclus)',                          ref: 'CGI art. 142' },
        { code: 'D4',  label: 'Conditions de déductibilité TVA (NIU + FCA + régime + système DGI + non-espèces + 2 ex.)', ref: 'CGI art. 143' },
        { code: 'D6',  label: 'Exclusions du droit à déduction (logement, restauration, etc.)',  ref: 'CGI art. 144' },
        { code: 'D15', label: 'Recoupement TVA collectée mensuelle GL ↔ déclaration',            ref: 'Cross-control' },
        { code: 'C2',  label: 'Acomptes IS mensuels = 2 % CA (réel)',                            ref: 'CGI art. 21' },
        { code: 'E4',  label: 'Versement IRPP retenu : 15 du mois suivant',                      ref: 'CGI art. 82' },
      ]}
    />
  );
}
