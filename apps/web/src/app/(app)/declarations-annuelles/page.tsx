import { PlaceholderModule } from '@/components/placeholder-module';

export default function AnnualPage() {
  return (
    <PlaceholderModule
      title="Rapprochement des déclarations annuelles (DSF)"
      description="Comparaison ligne à ligne entre la DSF et la balance générale + grand livre, reconstitution du résultat fiscal."
      upcomingControls={[
        { code: 'C1',  label: 'Taux IS : 25 % si CA ≤ 3 Mrd, sinon 30 %',                       ref: 'CGI art. 17 + 17 bis' },
        { code: 'C3',  label: 'Minimum de perception : IS ≥ 2 % CA précédent',                  ref: 'CGI art. 22-23' },
        { code: 'C17', label: 'Report déficitaire ≤ 4 ans (6 banques)',                          ref: 'CGI art. 12' },
        { code: 'C9',  label: 'Plafond dons : 0,5 % CA / clubs sportifs : 5 %',                  ref: 'CGI art. 7-A-5' },
        { code: 'C14', label: 'Intérêts CC associés : capital × 1,5 + 25 % résultat',           ref: 'CGI art. 7-B' },
        { code: 'G1',  label: 'CA TVA mensuel ≈ CA classe 70 ≈ CA DSF',                          ref: 'Cross-control' },
      ]}
    />
  );
}
