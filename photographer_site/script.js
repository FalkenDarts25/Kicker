// Einfaches Beispiel-Skript für das Kontaktformular
// Dieses Skript verhindert das Standard-Verhalten des Formulars
// und zeigt stattdessen eine Meldung an.
document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('contact-form');
    if (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            alert('Vielen Dank für deine Nachricht!');
            form.reset();
        });
    }
});
