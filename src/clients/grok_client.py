#!/usr/bin/env python3
"""
Grok LLM API Client
A Python program that integrates with xAI's Grok language model API.
"""

import openai
import os
import sys
from typing import List, Dict, Optional
import json


class GrokClient:
    """
    A client for interacting with xAI's Grok language model API.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Grok client.
        
        Args:
            api_key: xAI API key. If not provided, will try to get from XAI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("XAI_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "API key is required. Set XAI_API_KEY environment variable or pass api_key parameter."
            )
        
        # Initialize OpenAI client configured for xAI's API
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url="https://api.x.ai/v1"
        )
        
        # Available Grok models
        self.available_models = [
            "grok-4-latest",
            "grok-3-latest",
            "grok-2-latest"
        ]
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str = "grok-4-latest",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> str:
        """
        Generate a chat completion using Grok.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            model: Grok model to use
            temperature: Controls randomness (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters for the API call
            
        Returns:
            Generated response text
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            return response.choices[0].message.content
            
        except openai.APIError as e:
            if e.status_code == 429:
                raise Exception("Rate limit exceeded. Please try again later.")
            elif e.status_code == 401:
                raise Exception("Invalid API key. Please check your XAI_API_KEY.")
            else:
                raise Exception(f"API error: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error: {e}")
    
    def chat_completion_with_tokens(
        self,
        messages: List[Dict[str, str]],
        model: str = "grok-4-latest",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs
    ) -> tuple[str, dict]:
        """
        Generate a chat completion using Grok and return response with token usage.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            model: Grok model to use
            temperature: Controls randomness (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters for the API call
            
        Returns:
            Tuple of (response_text, token_usage_dict)
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            response_text = response.choices[0].message.content
            
            # Extract all available token usage information from the API response
            # The Grok API uses OpenAI-compatible format, which provides:
            # - prompt_tokens: total input tokens (includes cached + non-cached)
            # - completion_tokens: final output tokens (the answer)
            # - total_tokens: total tokens used (may include thinking/reasoning tokens)
            # - prompt_cache_hit_tokens: cached input tokens (if available, typically cheaper)
            # For reasoning models, there may be additional "thinking" tokens that should be
            # counted as output tokens for pricing purposes (they cost the same as output)
            usage = response.usage
            prompt_tokens = getattr(usage, 'prompt_tokens', 0)
            completion_tokens = getattr(usage, 'completion_tokens', 0)
            total_tokens = getattr(usage, 'total_tokens', 0)
            
            token_usage = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': total_tokens,
            }
            
            # Check for cached token fields (various possible field names)
            # Standard OpenAI format uses 'prompt_cache_hit_tokens' for cached tokens
            # Some APIs may use alternative names like 'cached_tokens' or 'cached_input_tokens'
            cached_count = 0
            if hasattr(usage, 'prompt_cache_hit_tokens'):
                cached_count = usage.prompt_cache_hit_tokens
                token_usage['cached_tokens'] = cached_count
                token_usage['cached_input_tokens'] = cached_count
                token_usage['prompt_cache_hit_tokens'] = cached_count
            elif hasattr(usage, 'cached_tokens'):
                cached_count = usage.cached_tokens
                token_usage['cached_tokens'] = cached_count
                token_usage['cached_input_tokens'] = cached_count
            elif hasattr(usage, 'cached_input_tokens'):
                cached_count = usage.cached_input_tokens
                token_usage['cached_tokens'] = cached_count
                token_usage['cached_input_tokens'] = cached_count
            
            # Also check for input_tokens and output_tokens (alternative naming)
            # Some APIs may provide these as separate fields
            if hasattr(usage, 'input_tokens'):
                token_usage['input_tokens'] = usage.input_tokens
            if hasattr(usage, 'output_tokens'):
                token_usage['output_tokens'] = usage.output_tokens
            
            # For reasoning models, there may be "thinking" tokens not included in completion_tokens
            # These should be counted as output tokens for pricing (they cost $0.50/1M like output)
            # Calculate thinking tokens as: total_tokens - prompt_tokens - completion_tokens
            # If this is positive, add it to output tokens
            accounted_tokens = prompt_tokens + completion_tokens
            if total_tokens > accounted_tokens:
                thinking_tokens = total_tokens - accounted_tokens
                # Add thinking tokens to output tokens (they're priced the same)
                token_usage['thinking_tokens'] = thinking_tokens
                # Update completion_tokens to include thinking tokens for cost calculation
                token_usage['completion_tokens'] = completion_tokens + thinking_tokens
                token_usage['output_tokens'] = completion_tokens + thinking_tokens
            
            return response_text, token_usage
            
        except openai.APIError as e:
            if e.status_code == 429:
                raise Exception("Rate limit exceeded. Please try again later.")
            elif e.status_code == 401:
                raise Exception("Invalid API key. Please check your XAI_API_KEY.")
            else:
                raise Exception(f"API error: {e}")
        except Exception as e:
            raise Exception(f"Unexpected error: {e}")
    
    def simple_query(self, query: str, model: str = "grok-4-latest") -> str:
        """
        Send a simple query to Grok and get a response.
        
        Args:
            query: The question or prompt to send
            model: Grok model to use
            
        Returns:
            Generated response text
        """
        messages = [
            {"role": "user", "content": query}
        ]
        
        return self.chat_completion(messages, model=model)
    
    def simple_query_with_tokens(self, query: str, model: str = "grok-4-latest") -> tuple[str, dict]:
        """
        Send a simple query to Grok and get a response with token usage.
        
        Args:
            query: The question or prompt to send
            model: Grok model to use
            
        Returns:
            Tuple of (response_text, token_usage_dict)
        """
        messages = [
            {"role": "user", "content": query}
        ]
        
        return self.chat_completion_with_tokens(messages, model=model)
    
    def conversational_chat(
        self,
        conversation_history: List[Dict[str, str]],
        new_message: str,
        model: str = "grok-4-latest"
    ) -> str:
        """
        Continue a conversation with Grok.
        
        Args:
            conversation_history: Previous messages in the conversation
            new_message: New message to add
            model: Grok model to use
            
        Returns:
            Generated response text
        """
        messages = conversation_history + [{"role": "user", "content": new_message}]
        return self.chat_completion(messages, model=model)
    
    def get_available_models(self) -> List[str]:
        """
        Get list of available Grok models.
        
        Returns:
            List of available model names
        """
        return self.available_models.copy()


def main():
    """
    Main function demonstrating Grok API usage.
    """
    print("Grok LLM API Client Demo")
    print("=" * 40)
    
    try:
        # Initialize the client
        grok = GrokClient()
        
        print(f"Available models: {', '.join(grok.get_available_models())}")
        print()
        
        # Example 1: Simple query
        print("Example 1: Simple Query")
        print("-" * 20)
        query = "What is artificial intelligence and how does it work?"
        print(f"Query: {query}")
        
        response = grok.simple_query(query)
        print(f"Response: {response}")
        print()
        
        # Example 2: Conversational chat
        print("Example 2: Conversational Chat")
        print("-" * 30)
        
        conversation = [
            {"role": "system", "content": "You are a helpful AI assistant specializing in technology."},
            {"role": "user", "content": "Tell me about machine learning."},
            {"role": "assistant", "content": "Machine learning is a subset of artificial intelligence that enables computers to learn and make decisions from data without being explicitly programmed for every task."}
        ]
        
        new_message = "What are the main types of machine learning?"
        print(f"New message: {new_message}")
        
        response = grok.conversational_chat(conversation, new_message)
        print(f"Response: {response}")
        print()
        
        # Example 3: Interactive mode
        print("Example 3: Interactive Mode")
        print("-" * 25)
        print("Enter your questions (type 'quit' to exit):")
        
        while True:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            if user_input:
                try:
                    response = grok.simple_query(user_input)
                    print(f"Grok: {response}")
                except Exception as e:
                    print(f"Error: {e}")
    
    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("\nTo fix this:")
        print("1. Get an API key from https://console.x.ai/")
        print("2. Set the XAI_API_KEY environment variable:")
        print("   export XAI_API_KEY='your_api_key_here'")
        print("   (On Windows: set XAI_API_KEY=your_api_key_here)")
        sys.exit(1)
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
