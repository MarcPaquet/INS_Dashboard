"""
Authentication utilities for INS Dashboard.

Provides password hashing and verification using bcrypt.
"""
import bcrypt


def hash_password(plain_password: str) -> str:
    """
    Hash a plain text password using bcrypt.
    
    Args:
        plain_password: The plain text password to hash
        
    Returns:
        The hashed password as a string
        
    Example:
        >>> hashed = hash_password("MySecurePassword123")
        >>> print(len(hashed))  # Should be 60 characters
        60
    """
    # Convert string to bytes
    password_bytes = plain_password.encode('utf-8')
    
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    
    # Convert bytes back to string for storage
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against a hashed password.
    
    Args:
        plain_password: The plain text password to verify
        hashed_password: The hashed password to check against
        
    Returns:
        True if the password matches, False otherwise
        
    Example:
        >>> hashed = hash_password("MyPassword")
        >>> verify_password("MyPassword", hashed)
        True
        >>> verify_password("WrongPassword", hashed)
        False
    """
    try:
        # Convert strings to bytes
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        
        # Check password
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except (ValueError, AttributeError) as e:
        # Handle encoding errors or invalid hash format
        print(f"Password verification error: {e}")
        return False


if __name__ == "__main__":
    # Test the functions
    print("=== Testing Password Hashing ===")
    
    test_password = "TestPassword123"
    print(f"Original password: {test_password}")
    
    # Hash the password
    hashed = hash_password(test_password)
    print(f"Hashed password: {hashed}")
    print(f"Hash length: {len(hashed)} characters")
    
    # Verify correct password
    is_valid = verify_password(test_password, hashed)
    print(f"Correct password verification: {is_valid}")
    
    # Verify incorrect password
    is_invalid = verify_password("WrongPassword", hashed)
    print(f"Wrong password verification: {is_invalid}")
    
    print("\nPassword hashing utilities working correctly!")
