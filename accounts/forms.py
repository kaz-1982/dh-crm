from django.contrib.auth.forms import AuthenticationForm
from django.forms import PasswordInput, TextInput


class StyledAuthenticationForm(AuthenticationForm):
    """標準の AuthenticationForm に CSS クラスとオートフォーカスを足しただけのもの。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget = TextInput(
            attrs={"class": "input", "autofocus": True, "autocomplete": "username"}
        )
        self.fields["password"].widget = PasswordInput(
            attrs={"class": "input", "autocomplete": "current-password"}
        )
