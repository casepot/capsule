import { jest } from '@jest/globals';

describe('Simple Test', () => {
  it('should run a basic test', () => {
    expect(1 + 1).toBe(2);
  });
  
  it('should handle async tests', async () => {
    const result = await Promise.resolve('test');
    expect(result).toBe('test');
  });
});