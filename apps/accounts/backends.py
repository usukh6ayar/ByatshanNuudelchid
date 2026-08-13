"""Authentication backend — RFP §3.1.

Teachers log in with a username or email, guardians with a phone number or
email. That is one login form resolving three identifier types, not three
separate login systems.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class MultiIdentifierBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("identifier")
        if not identifier or not password:
            return None

        identifier = identifier.strip()

        try:
            user = UserModel.objects.get(
                Q(username__iexact=identifier)
                | Q(email__iexact=identifier)
                | Q(phone=identifier)
            )
        except UserModel.DoesNotExist:
            # Run the hasher anyway so response timing does not reveal
            # whether the identifier exists.
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # Should be impossible: all three fields are unique. Treat any
            # ambiguity as a failure rather than guessing.
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
