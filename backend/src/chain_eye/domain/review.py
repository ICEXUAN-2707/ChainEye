class FactNotFoundError(LookupError):
    pass

class FactRevisionConflictError(ValueError):
    def __init__(self,current_revision):
        self.current_revision=current_revision
        super().__init__(f'current revision is {current_revision}')

class EvidenceScopeError(ValueError):
    pass

class FactScopeError(ValueError):
    pass
